from typing import List
import logging
from ipaddress import IPv4Address, IPv4Network
from jinja2 import Environment, FileSystemLoader
import argparse
import os

logger = logging.getLogger(__name__)

vlans_counter = 0

TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
print(TEMPLATES_DIR)

# We use 10.0.0.0/8 by default and subnets of /24
class VLAN:
    def __init__(self):
        global vlans_counter
        vlans_counter += 1
        self.id = vlans_counter

        second_octet = int(self.id / 256)
        third_octet = self.id % 256

        network_str = f"10.{second_octet}.{third_octet}.0/24"
        self.network = IPv4Network(network_str)

        logger.info(f"VLAN {self.id} created assigned to IP network {self.network}")

class RoutedVLAN:
    def __init__(self, vlan : VLAN, ip_address : IPv4Address) -> None:
        assert isinstance(vlan, VLAN)
        self.vlan = vlan
        self.ip_address = ip_address

class Site:
    def __init__(self, name : str, num_distributions : int, num_access : int) -> None:
        self.name = name
        self.distributions : List["Distribution"] = []
        logger.info(f"Site {name} created")
        logger.debug(f"Creating WAN device")
        self.wan = Switch(f"{name}-wan-0")
        logger.debug(f"Creating distributions")
        for n in range(0, num_distributions):
            distribution_name = f"{name}-dist-{n}"
            distribution = Distribution(self, distribution_name, num_access, self.wan.routed_vlans[0].vlan, self.wan.routed_vlans[0].vlan.network[2+n])
            # add default route on distribution towards WAN router
            default_route = Route(IPv4Network("0.0.0.0/0"), self.wan.routed_vlans[0].ip_address)
            distribution.routing_table.add(default_route)
            # add route to distribution vlan and all vlans underneath
            for routing_entry in distribution.routing_table.routes:
                if routing_entry.dst_network == IPv4Network("0.0.0.0/0"):
                    # skip default routes
                    continue
                self.wan.routing_table.add(Route(routing_entry.dst_network, self.wan.routed_vlans[0].vlan.network[2+n]))
            self.distributions.append(distribution)

    def dump_to_directory(self, directory):
        directory = directory if directory else self.name
        # WAN router
        self.wan.dump_to_director(directory)
        # distribution switches with accesses
        for distr in self.distributions:
            distr.dump_to_director(directory)
            for access in distr.accesses:
                access.dump_to_director(directory)

class Route:
    def __init__(self, dst_network : IPv4Network, next_hop : IPv4Address) -> None:
        self.dst_network = dst_network
        self.next_hop = next_hop

    def __repr__(self) -> str:
        return f"{self.dst_network} via {self.next_hop}"

    def print(self) -> None:
        print(repr(self))

class RoutingTable:
    def __init__(self):
        self.routes : List[Route] = []
        pass

    def __repr__(self) -> str:
        ret = []
        for route in self.routes:
           ret.append(repr(route))

        return "\n".join(ret)

    def add(self, route: Route):
        self.routes.append(route)

    def remove(self, route: Route):
        assert route in self.routes
        self.routes.remove(route)

    def show_ip_route(self) -> str:
        pass

class Switch:
    def __init__(self, name : str) -> None:
        self.name = name

        # Creating default VLAN where switch has first IP address of the given range
        vlan = VLAN()
        ip = vlan.network[1]

        # creating SVIs and routing table
        self.routed_vlans : List[RoutedVLAN] = [RoutedVLAN(vlan, ip)]
        self.routing_table = RoutingTable()

        logger.info(f"Switch {name} created")

    def show_ip_interface(self) -> str:
        env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        template = env.get_template('show ip interface')
        return template.render(routed_vlans = self.routed_vlans)

    def show_interfaces(self) -> str:
        env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        template = env.get_template('show interfaces')
        return template.render(routed_vlans = self.routed_vlans)

    def show_ip_route(self) -> str:
        env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        template = env.get_template('show ip route')
        return template.render(routed_vlans = self.routed_vlans, routing_table = self.routing_table.routes)

    commands = {
        "show ip route" : show_ip_route,
        "show interfaces" : show_interfaces,
        "show ip interface" : show_ip_interface
    }

    def dump_to_director(self, dir : str):
        dir_name = os.path.join(dir, self.name)
        os.makedirs(dir_name, exist_ok=True)

        # let's dump all supported commands
        for command_name, command_func in self.commands.items():
            command_output = command_func(self)
            file_path = os.path.join(dir_name, command_name)

            with open(file_path, "w") as fp:
                fp.write(command_output)

class Distribution(Switch):
    def __init__(self, site : Site, name : str, num_access : int, wan_vlan : VLAN, wan_ip : IPv4Address) -> None:
        super().__init__(name)
        self.site = site
        self.accesses : List["Access"] = []

        self.routed_vlans.append(RoutedVLAN(wan_vlan, wan_ip))

        logger.debug("Creating accesses")
        for n in range(0, num_access):
            access_name = f"{self.name}-access-{n}"
            access = Access(self, access_name, self.routed_vlans[0].vlan, self.routed_vlans[0].vlan.network[n+2])
            route = Route(access.routed_vlans[0].vlan.network, self.routed_vlans[0].vlan.network[n+2])
            self.routing_table.add(route)
            # default route on access should point to distribution
            default_route = Route(IPv4Network("0.0.0.0/0"), self.routed_vlans[0].ip_address)
            access.routing_table.add(default_route)
            self.accesses.append(access)

class Access(Switch):
    def __init__(self, distribution : Distribution, name : str, distribution_vlan : VLAN, distribution_ip : IPv4Network) -> None:
        super().__init__(name)
        self.distribution = distribution
        self.routed_vlans.append(RoutedVLAN(distribution_vlan, distribution_ip))

def main()->None:
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser(description='Generate network topology (mainly outputs).')
    parser.add_argument('--distributions', type=int,
                        help='number of distribution switches', required=True)
    parser.add_argument('--accesses', type=int,
                        help='number of access switches', required=True)
    parser.add_argument('--site-name', type=str,
                        help='number of access switches', required=True)
    args = parser.parse_args()

    site = Site(args.site_name, args.distributions, args.accesses)
    site.dump_to_directory(args.site_name)
    logger.info(f"Files saved in directory {args.site_name}")

if __name__ == '__main__':
    main()
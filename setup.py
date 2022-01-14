from setuptools import setup

setup(
    name='lazynetgen',
    version='0.1',
    packages=['lazynetgen'],
    url='',
    license='',
    author='Piotr Kupisiewicz',
    author_email='pkupisie@cisco.com',
    description='',
    install_requires=['jinja2'],
    entry_points={
    'console_scripts': [
        'lazynetgen = lazynetgen.main:main',
    ]},
    include_package_data = True,
    package_data={"lazynetgen" : ["templates/*"]}
)

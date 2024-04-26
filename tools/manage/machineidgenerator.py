#!/usr/bin/env python
"""
Machine ID Generator

This module generates a random ID to be used in DNS to map individual machine IPs.
It provides a class, MachineIDGenerator, which encapsulates the functionality for generating
and validating machine IDs and associated DNS configurations.

Classes:
    MachineIDGenerator:
        A class to generate random IDs and associated DNS configurations.

        Methods:
            __init__(length: int) -> None:
                Initializes the MachineIDGenerator instance with the specified length for the random ID.

            random_id_generator() -> None:
                Generates a random ID of the specified length.

            validate() -> bool:
                Validates the generated DNS configurations.

            unique() -> bool:
                Checks if the generated DNS configurations are unique.

            validate_network() -> List[str]:
                Validates the MACHINE_NETWORK environment variable.

            validate_prefix() -> List[str]:
                Validates the MACHINE_PREFIX environment variable.

            validate_input() -> None:
                Validates the input parameters MACHINE_NETWORK and MACHINE_PREFIX.

            print_config() -> None:
                Prints the configuration settings.

            print_output(output_path: str) -> None:
                Prints the generated machine ID and FQDN and creates a setup script.

            __call__(output_path: str = "output") -> None:
                Executes the machine ID generation process.

            generate() -> None:
                Generates the machine ID and associated DNS configurations.

Usage:
    The module can be executed as a standalone script to generate a machine ID and associated DNS configurations.
    It reads the environment variables MACHINE_NETWORK and MACHINE_PREFIX to determine the network and prefix for
    the DNS configurations.

Example:
    $ python machine_id_generator.py
"""

import os
import secrets
import shutil
import string

import CloudFlare
import validators
from CloudFlare.exceptions import CloudFlareAPIError
from dotenv import load_dotenv

from tools.ddns.agent import DDNSAgentv6

load_dotenv()


class MachineIDGenerator(object):
    """
    Generates random ID to be used in DNS to map individual machine IPs.

    Attributes:
        random_id_length (int): The length of the random ID.

    Methods:
        Other methods are described in the class-level docstring.
    """

    def __init__(self, length: int, machine_network: str | None = None, machine_prefix: str | None = None) -> None:
        """
        Initializes the MachineIDGenerator instance with the specified length for the random ID.

        Args:
            length (int): The length of the random ID.
        """
        self.random_id_length = length
        self.machine_network = machine_network
        self.machine_prefix = machine_prefix

    def random_id_generator(self) -> None:
        """
        Generates a random ID of the specified length.
        """
        self.random_id = "".join(
            secrets.choice(string.ascii_lowercase) for _ in range(self.random_id_length)
        )

    def validate(self) -> bool:
        """
        Validates the generated DNS configurations.

        Returns:
            bool: True if the configurations are valid, False otherwise.
        """
        if not validators.domain(self.fqdn):
            return False
        if not self.unique():
            return False
        return True

    def unique(self) -> bool:
        """
        Checks if the generated DNS configurations are unique.

        Returns:
            bool: True if the configurations are unique, False otherwise.
        """
        try:
            params = {"name": self.fqdn, "match": "all", "type": "AAAA"}
            dns_records = self.cf.zones.dns_records.get(self.zone_id, params=params)
        except CloudFlareAPIError as e:
            exit(
                "Error: /zones/dns_records %s - %d %s - api call failed"
                % (self.fqdn, e, e)
            )
        if len(dns_records) != 0:
            return False
        return True

    def validate_network(self) -> list[str]:
        """
        Validates the MACHINE_NETWORK environment variable.

        Returns:
            List[str]: A list of error messages, if any.
        """
        errors: list[str] = []
        if self.machine_network is None:
            return ['Error: "MACHINE_NETWORK" not set']
        if not validators.domain(self.machine_network):
            errors.append('Error: "MACHINE_NETWORK" not set to a proper FQDN')
        if len(self.machine_network) > 253 - 63:
            errors.append('Error: "MACHINE_NETWORK" length is too long')
            errors.append(
                'Hint: For proper functioning cap "MACHINE_NETWORK" length to '
                + str(253 - 63)
            )
        return errors

    def validate_prefix(self) -> list[str]:
        """
        Validates the MACHINE_PREFIX environment variable.

        Returns:
            List[str]: A list of error messages, if any.
        """
        errors: list[str] = []
        if self.machine_prefix is None:
            return ['Error: "MACHINE_PREFIX" not set']
        label_length = len(self.machine_prefix) + 1 + self.random_id_length
        if (
            not validators.hostname(
                self.machine_prefix,
                skip_ipv6_addr=True,
                skip_ipv4_addr=True,
                may_have_port=False,
                rfc_2782=True,
            )
            or self.machine_prefix.find(".") != -1
        ):
            errors.append(
                'Error: "MACHINE_PREFIX" not set to a proper "hostname" component'
            )
        if label_length > 63:
            errors.append(
                'Error: generated "label" length will exceed the limit please reduce\n\t'
                + '"MACHINE_PREFIX" to match the length requirements of a DNS label'
            )
            errors.append(
                "Hint: DNS Label length is capped at 63 characters.\n\t"
                + '"MACHINE_PREFIX" is capped at '
                + str(63 - self.random_id_length + 1)
                + " characters"
            )
        return errors

    def validate_input(self) -> None:
        """
        Validates the input parameters MACHINE_NETWORK and MACHINE_PREFIX.
        """
        errors: list[str] = []
        if self.machine_network is None:
            errors.append('Error: "MACHINE_NETWORK" not set')
        else:
            self.base_domain = self.machine_network
            errors.extend(self.validate_network())

        if self.machine_prefix is None:
            errors.append('Error: "MACHINE_PREFIX" not set')
        else:
            self.prefix = self.machine_prefix
            errors.extend(self.validate_prefix())

        if (
            self.machine_network is not None
            and self.machine_prefix is not None
            and self.machine_network != ""
            and self.machine_prefix != ""
        ):
            label_length = (
                len(self.machine_prefix) + 1 + self.random_id_length
            )  # + 1 for one "-" char
            if label_length + len(self.machine_network) > 253:
                errors.append(
                    'Error: generated "hostname" length will exceed the limit please reduce either '
                    + 'or both of\n\t"MACHINE_PREFIX" or "MACHINE_NETWORK" to match the length'
                    + " requirements of a FQDN"
                )
                errors.append("Hint: FQDN length is capped at 253 characters")

        if len(errors) > 0:
            exit("\n".join(errors))

    def print_config(self) -> None:
        """
        Prints the configuration settings.
        """
        print("Running Generator with following config:")
        print("\tMACHINE_NETWORK: {}".format(self.machine_network))
        print("\tMACHINE_PREFIX: {}".format(self.machine_prefix))
        print("\tRANDOM LENGTH: {}".format(self.random_id_length))
        print("\tCF ZONE ID: {}".format(self.zone_id))

    def print_output(self,output_path: str) -> None:
        """
        Prints the generated machine ID and FQDN and creates a setup script.

        Args:
            output_path (str): The output path for the setup script.
        """
        print("GENERATED Machine ID: " + self.host_label)
        print("GENERATED FQDN: " + self.fqdn)
        print(
            "Please add the following to your terminal profile file of the host machine:"
        )
        print()
        print(
            "\texport DDNS_HOST={}\n\texport MACHINE_ID={}".format(
                self.fqdn, self.host_label
            )
        )
        if os.path.isdir(output_path):
            shutil.rmtree(output_path)
        os.makedirs(output_path, 777)
        with open(os.path.join(output_path, "setup.sh"), "w") as script:
            commands: list[str] = []
            commands.append("#!/bin/bash\n\n")
            commands.append("export MACHINE_NET={}\n".format(self.base_domain))
            commands.append("export MACHINE_ID={}\n".format(self.host_label))
            commands.append("export DDNS_HOST={}\n".format(self.fqdn))
            script.writelines(commands)

    def __call__(self, output_path: str = "output") -> None:
        """
        Executes the machine ID generation process.

        Args:
            output_path (str, optional): The output path for the setup script. Defaults to "output".
        """
        if self.machine_network is None:
            self.machine_network = os.getenv("MACHINE_NETWORK")
        if self.machine_prefix is None:
            self.machine_prefix = os.getenv("MACHINE_PREFIX")
        self.validate_input()

        zone_name = ".".join(self.base_domain.split(".")[-2:])
        self.cf = CloudFlare.CloudFlare()
        try:
            zone_id = os.getenv("CF_ZONE_ID")
            if zone_id is None or zone_id == "":
                del zone_id
                params = {"name": zone_name}
                zones = self.cf.zones.get(params=params)
            else:
                self.zone_id = zone_id
                params = {"id": self.zone_id}
                zones = self.cf.zones.get(params=params)
        except CloudFlareAPIError as e:
            exit("Error: /zones %d %s - api call failed" % (e, e))
        except Exception as e:
            exit("Error: /zones.get - %s - api call failed" % (e))

        if isinstance(zones, list):
            if len(zones) == 0:
                exit("Error: /zones.get - %s - zone not found" % (zone_name))
            elif len(zones) != 1:
                exit(
                    "Error: /zones.get - %s - api call returned %d items"
                    % (zone_name, len(zones))
                )
            else:
                self.zone_id: str = zones[0]["id"]

        self.print_config()
        self.generate()
        self.print_output(output_path)

    def generate(self) -> None:
        """
        Generates the machine ID and associated DNS configurations.
        """
        while True:
            self.random_id_generator()
            self.host_label = self.prefix + "-" + self.random_id
            self.fqdn = ".".join([self.host_label, self.base_domain])
            if self.validate():
                ddns = DDNSAgentv6()
                ddns.do_dns_update(self.cf, self.zone_id, self.fqdn, "::1")
                self.machine_id = self.host_label
                self.ddns_host = self.fqdn
                break


if __name__ == "__main__":
    agent = MachineIDGenerator(8)
    agent()

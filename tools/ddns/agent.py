#!/usr/bin/env python
"""
DDNS Updater Agent

This script updates DNS records with IPv6 addresses using supported DNS providers' APIs.

Supported providers:
  - Cloudflare
  - DigitalOcean
"""

import json
import os
import sys
from enum import Enum

import CloudFlare
import requests
import validators
from CloudFlare.exceptions import CloudFlareAPIError
from dotenv import load_dotenv
from pydo import Client

load_dotenv()


class DDNSUpdateError(Exception):
    """Exception raised for errors during DDNS update."""

    pass


class DDNSEngines(Enum):
    """Supported DNS service providers."""

    CLOUDFLARE = "cf"
    DIGITALOCEAN = "do"


class DDNSAgentv6(object):
    """
    DDNS Updater with IPv6 Support

    This class handles updating DNS records with IPv6 addresses for
    supported DNS providers. It retrieves the current IPv6 address of the machine,
    parses a configuration file specifying the DNS zones and hostnames to update
    on each provider, and communicates with the provider APIs to perform the update.
    """

    @classmethod
    def my_ipv6_address(cls) -> str:
        """
        Retrieve the IPv6 address of the current machine.

        This method attempts to retrieve the IPv6 address from several public APIs.
        If none of the APIs respond with a valid IPv6 address, an error is raised.

        Args:
            None

        Returns:
            str: The IPv6 address of the current machine.

        Raises:
            Exception: If unable to retrieve the IPv6 address.
        """

        ip_finders = [
            "https://api6.ipify.org/",
            "https://www.trackip.net/ip",
            "https://ipapi.co/ip",
        ]
        ip_address = str()
        err_outputs = list()
        for url in ip_finders:
            try:
                ip_address = requests.get(url, timeout=5).text
            except Exception as e:
                err_outputs.append({"api": url, "output": str(e)})
                continue

            if validators.ipv6(ip_address):  # type: ignore
                break

            err_outputs.append({"api": url, "output": ip_address})

        if not validators.ipv6(ip_address):  # type: ignore
            print(
                "Error: Could not find ipv6 address"
                + json.dumps(err_outputs, indent=4),
                file=sys.stderr,
            )
            exit(1)

        return ip_address

    @classmethod
    def cf_dns_update(
        cls, cf: CloudFlare.CloudFlare, zone_id: str, dns_name: str, ip_address: str
    ) -> None:
        """
        Update DNS records with the specified IPv6 address for Cloudflare.

        This method updates the DNS record for the given `dns_name` within the Cloudflare zone identified by `zone_id`
        to the provided `ip_address`. It first checks if there's an existing record with the same name. If there is,
        it updates the record's content with the new IP address. Otherwise, a new AAAA record is created.

        Args:
            cf (CloudFlare.CloudFlare): A Cloudflare client object.
            zone_id (str): The ID of the Cloudflare zone to update.
            dns_name (str): The DNS hostname to update.
            ip_address (str): The new IPv6 address to set.

        Raises:
            DDNSUpdateError: If unable to update the DNS record.
        """

        try:
            params = {"name": dns_name, "match": "all", "type": "AAAA"}
            dns_records = cf.zones.dns_records.get(zone_id, params=params)
        except CloudFlareAPIError as e:
            raise DDNSUpdateError(
                "Error: /zones/dns_records %s - %d %s - api call failed"
                % (dns_name, e, e)
            ) from e

        updated = False

        # update the record - unless it's already correct
        for dns_record in dns_records:
            old_ip_address = dns_record["content"]

            if ip_address == old_ip_address:
                print("UNCHANGED: %s %s" % (dns_name, ip_address))
                updated = True
                continue

            proxied_state = dns_record["proxied"]

            # Yes, we need to update this record
            dns_record_id = dns_record["id"]
            dns_record = {
                "name": dns_name,
                "type": "AAAA",
                "content": ip_address,
                "proxied": proxied_state,
            }
            try:
                dns_record = cf.zones.dns_records.put(
                    zone_id, dns_record_id, data=dns_record
                )
                params = {"name": dns_name, "match": "all", "type": "AAAA"}
                dns_records = cf.zones.dns_records.get(zone_id, params=params)
                if dns_records[0]["content"] == ip_address:
                    updated = True
                else:
                    raise DDNSUpdateError("Error: Record was not updated")
            except CloudFlareAPIError as e:
                raise DDNSUpdateError(
                    "Error: /zones.dns_records.put %s - %d %s - api call failed"
                    % (dns_name, e, e)
                ) from e
            print("UPDATED: %s %s -> %s" % (dns_name, old_ip_address, ip_address))

        if updated:
            return

        # no existing dns record to update - so create dns record
        dns_record = {
            "name": dns_name,
            "type": "AAAA",
            "content": ip_address,
            "ttl": 60,
        }
        try:
            dns_record = cf.zones.dns_records.post(zone_id, data=dns_record)
            params = {"name": dns_name, "match": "all", "type": "AAAA"}
            dns_records = cf.zones.dns_records.get(zone_id, params=params)
            if dns_records[0]["content"] != ip_address:
                print("Error: Record was not created", file=sys.stderr)
                return
        except CloudFlareAPIError as e:
            raise DDNSUpdateError(
                "Error: /zones.dns_records.post %s - %d %s - api call failed"
                % (dns_name, e, e)
            ) from e
        print("CREATED: %s %s" % (dns_name, ip_address))

    @classmethod
    def do_dns_update(
        cls, do: Client, zone: str, dns_name: str, ip_address: str
    ) -> None:
        """
        Update DNS records with the specified IPv6 address for DigitalOcean.

        This method updates the DNS record for the given `dns_name` within the DigitalOcean zone identified by `zone`
        to the provided `ip_address`. It first checks if there's an existing record with the same name. If there is,
        it updates the record's content with the new IP address. Otherwise, a new AAAA record is created.

        Args:
            do (Client): A DigitalOcean client object.
            zone (str): The name of the DigitalOcean zone to update.
            dns_name (str): The DNS hostname to update.
            ip_address (str): The new IPv6 address to set.

        Raises:
            DDNSUpdateError: If unable to update the DNS record.
        """

        dns_records = list()

        if dns_name.find(zone) == -1:
            print("Error: %s not part of Zone %s" % (dns_name, zone), file=sys.stderr)
            return

        fqdn = dns_name
        dns_name = dns_name.removesuffix("." + zone)

        try:
            resp = do.domains.list_records(domain_name=zone, name=fqdn, type="AAAA")
            if resp.get("domain_records") is not None:
                dns_records = resp.get("domain_records")
        except Exception as e:
            raise DDNSUpdateError(
                "Error: /zones/dns_records %s - %d %s - api call failed"
                % (dns_name, e, e)
            ) from e

        updated = False

        # update the record - unless it's already correct
        if dns_records is None:
            dns_records = list()
        for dns_record in dns_records:
            old_ip_address = dns_record["data"]

            if ip_address == old_ip_address:
                print("UNCHANGED: %s %s" % (dns_name, ip_address))
                updated = True
                continue

            # Yes, we need to update this record
            dns_record_id = dns_record["id"]
            dns_record = {
                "type": "AAAA",
                "name": dns_name,
                "data": ip_address,
                "priority": None,
                "port": None,
                "ttl": 60,
                "weight": None,
                "flags": None,
                "tag": None,
            }
            try:
                dns_record = do.domains.update_record(
                    domain_name=zone,
                    domain_record_id=dns_record_id,
                    body=dns_record,
                )
                if dns_record.get("domain_record") is not None:
                    updated = True
                else:
                    print("Error: Record was not updated", file=sys.stderr)
                    return
            except Exception as e:
                raise DDNSUpdateError(
                    "Error: /zones.dns_records.put %s - %d %s - api call failed"
                    % (dns_name, e, e)
                ) from e
            print("UPDATED: %s %s -> %s" % (dns_name, old_ip_address, ip_address))

        if updated:
            return

        # no existing dns record to update - so create dns record
        dns_record = {
            "type": "AAAA",
            "name": dns_name,
            "data": ip_address,
            "priority": None,
            "port": None,
            "ttl": 60,
            "weight": None,
            "flags": None,
            "tag": None,
        }
        try:
            dns_record = do.domains.create_record(domain_name=zone, body=dns_record)
            if dns_record.get("domain_record") is None:
                print("Error: Record was not created", file=sys.stderr)
                return
        except Exception as e:
            raise DDNSUpdateError(
                "Error: /zones.dns_records.post %s - %d %s - api call failed"
                % (dns_name, e, e)
            ) from e
        print("CREATED: %s %s" % (dns_name, ip_address))
        pass

    def call_cf(self, cftoken: str) -> None:
        """
        Updates DNS records for all configured Cloudflare zones and hostnames.

        This method performs the following steps to update DNS records for Cloudflare zones:

        1. Initializes a Cloudflare client object using the provided `cftoken`.
        2. Iterates through the `dns_names_cf` dictionary (populated from the configuration file).
            - For each zone:
                - Retrieves the zone ID using the `zone` name and the Cloudflare API.
                - Iterates through the list of hostnames (`dns_list`) associated with the zone.
                - For each hostname:
                    - Calls the `cf_dns_update` method to update the DNS record
                        with the retrieved IPv6 address (`self.ip_address`).
                    - Catches any `DDNSUpdateError` exceptions and appends them to an error list.

        3. Raises a `DDNSUpdateError` if there were any errors encountered during the update process.
            The raised error message will be a JSON-formatted string containing all the encountered errors.

        Args:
            self (DDNSAgentv6): An instance of the DDNSAgentv6 class.
            cftoken (str): The Cloudflare API token to use for communication.

        Raises:
            DDNSUpdateError: If any errors occur during the update process.
                The error message will be a JSON-formatted string containing details about the errors.
        """

        cf = CloudFlare.CloudFlare(token=cftoken)

        errors: list[str] = []

        for zone, dns_list in self.dns_names_cf.items():
            # grab the zone identifier
            try:
                params = {"name": zone}
                zones = cf.zones.get(params=params)
            except CloudFlareAPIError as e:
                errors.append("Error: /zones %d %s - api call failed" % (e, e))
                continue
            except Exception as e:
                errors.append("Error: /zones.get - %s - api call failed" % (e))
                continue

            if len(zones) == 0:
                errors.append("Error: /zones.get - %s - zone not found" % (zone))
                continue

            if len(zones) != 1:
                errors.append(
                    "Error: /zones.get - %s - api call returned %d items"
                    % (zone, len(zones))
                )
                continue

            zone_id = zones[0]["id"]

            for dns in dns_list:
                try:
                    self.cf_dns_update(cf, zone_id, dns, self.ip_address)
                except DDNSUpdateError as e:
                    errors.append("Error Updating %s: %s" % (e))

        if len(errors) != 0:
            raise DDNSUpdateError(json.dumps(errors, indent=4))

    def call_do(self, dotoken: str) -> None:
        """
        Updates DNS records for all configured DigitalOcean zones and hostnames.

        This method performs the following steps to update DNS records for DigitalOcean zones:

        1. Initializes a DigitalOcean client object using the provided `dotoken`.
        2. Iterates through the `dns_names_do` dictionary (populated from the configuration file).
            - For each zone:
                - Attempts to retrieve the zone details using the `do.domains.get` method.
                - If the zone is not found (`"not_found"` in response), a `DDNSUpdateError` is raised.
                - Otherwise, iterates through the list of hostnames (`dns_list`) associated with the zone.
                - For each hostname:
                    - Calls the `do_dns_update` method to update the DNS record
                        with the retrieved IPv6 address (`self.ip_address`).
                    - Catches any `DDNSUpdateError` exceptions and appends them to an error list.

        3. Raises a `DDNSUpdateError` if there were any errors encountered during the update process.
            The raised error message will be a JSON-formatted string containing all the encountered errors.

        Args:
            self (DDNSAgentv6): An instance of the DDNSAgentv6 class.
            dotoken (str): The DigitalOcean API token to use for communication.

        Raises:
            DDNSUpdateError: If any errors occur during the update process.
                The error message will be a JSON-formatted string containing details about the errors.
        """

        do = Client(token=dotoken)

        errors: list[str] = []

        for zone, dns_list in self.dns_names_do.items():
            try:
                zones = do.domains.get(zone)
                if zones.get("id") == "not_found":
                    raise DDNSUpdateError("Error: Zone %s Not Found" % (zone))

                for dns in dns_list:
                    try:
                        self.do_dns_update(do, zone, dns, self.ip_address)
                    except DDNSUpdateError as e:
                        errors.append("Error Updating %s: %s" % (e))
            except Exception as e:
                errors.append("DO Error %s" % (e))
            pass
        if len(errors) != 0:
            raise DDNSUpdateError(json.dumps(errors, indent=4))

    @staticmethod
    def line_inp_valid(test: list[str]) -> bool:
        """
        Validate the format of a line in the configuration file.

        This method checks if a line in the configuration file has the expected format:
        - Three elements separated by spaces.
        - The first element is a valid DNS service provider code ("cf" or "do").
        - The second and third elements are valid domain names.

        Args:
            test (list[str]): A list of strings representing a line from the configuration file.

        Returns:
            bool: True if the line is valid, False otherwise.
        """

        if len(test) != 3:
            return False
        if test[0] not in DDNSEngines._value2member_map_.keys():
            return False
        if not validators.domain(test[1]) or not validators.domain(test[2]):
            return False
        return True

    def parse_host_file(self) -> None:
        """
        Parse the configuration file and populate internal data structures.

        This method reads the configuration file specified by the `-c` argument or the
        `DDNS_CONFIG` environment variable. It validates each line's format and populates
        internal dictionaries `dns_names_cf` and `dns_names_do` for Cloudflare and DigitalOcean zones,
        respectively.

        Raises:
            DDNSUpdateError: If the configuration file cannot be found or is invalid.
        """
        self.dns_names_cf: dict[str, list[str]] = {}
        self.dns_names_do: dict[str, list[str]] = {}
        with open("./ddns.hosts") as file:
            for line in file:
                test = line.strip().split(" ")
                if self.line_inp_valid(test):
                    if test[0] == "cf":
                        self.dns_names_cf.setdefault(test[1], []).append(test[2])
                    elif test[0] == "do":
                        self.dns_names_do.setdefault(test[1], []).append(test[2])

        if len(self.dns_names_cf) == 0 and len(self.dns_names_do) == 0:
            print(
                "Error: No DDNS Host specified or set to a proper FQDN", file=sys.stderr
            )
            exit(1)

        print(
            "HOSTS TO UPDATE:\n\tCloudFlare: %s\n\tDigitalOcean: %s"
            % (self.dns_names_cf, self.dns_names_do)
        )

    def __call__(self) -> None:
        """
        Main entry point for the DDNS update process.

        This method performs the following steps to update DNS records:

        1. Retrieves the current IPv6 address of the machine using the `my_ipv6_address` method.
        2. Prints the retrieved IPv6 address to the console.
        3. Parses the configuration file using the `parse_host_file` method to populate internal data structures.
        4. Checks for the presence of the CLOUDFLARE_API_TOKEN environment variable:
            - If the token exists and there are configured zones in `dns_names_cf`:
                - Calls the `call_cf` method to update DNS records for Cloudflare zones.
            - Otherwise, prints a message indicating the environment variable is missing
                or there are no Cloudflare zones configured.
        5. Checks for the presence of the DIGITALOCEAN_TOKEN environment variable:
            - If the token exists and there are configured zones in `dns_names_do`:
                - Calls the `call_do` method to update DNS records for DigitalOcean zones.
            - Otherwise, prints a message indicating the environment variable is missing
                or there are no DigitalOcean zones configured.

        Args:
            self (DDNSAgentv6): An instance of the DDNSAgentv6 class.
        """

        self.ip_address = self.my_ipv6_address()
        print("MY IP: %s" % (self.ip_address))

        self.parse_host_file()

        cftoken = os.getenv("CLOUDFLARE_API_TOKEN")
        if cftoken is not None:
            if len(self.dns_names_cf.keys()) != 0:
                try:
                    self.call_cf(cftoken)
                except DDNSUpdateError as e:
                    print("Error: %s" % (e))
        else:
            print("CLOUDFLARE_API_TOKEN: type: %s" % (type(cftoken)))

        dotoken = os.getenv("DIGITALOCEAN_TOKEN")
        if dotoken is not None:
            if len(self.dns_names_do.keys()) != 0:
                try:
                    self.call_do(dotoken)
                except DDNSUpdateError as e:
                    print("Error: %s" % (e))
        else:
            print("DIGITALOCEAN_TOKEN: type: %s" % (type(dotoken)))

    def dns_update(
        self, engine: CloudFlare.CloudFlare | Client, zone: str, dns_name: str, ip_address: str
    ) -> None:
        if isinstance(engine, CloudFlare.CloudFlare):
            self.cf_dns_update(engine, zone, dns_name, ip_address)
        elif isinstance(engine, Client):
            self.do_dns_update(engine, zone, dns_name, ip_address)


if __name__ == "__main__":
    agent = DDNSAgentv6()
    agent()

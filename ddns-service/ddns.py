#!/usr/bin/env python
"""
DDNS Updater Agent

This script updates DNS records with IPv6 addresses using the Cloudflare API.
"""

import json
import sys
import os

import CloudFlare
import requests
import validators
from CloudFlare.exceptions import CloudFlareAPIError
from dotenv import load_dotenv

load_dotenv()


class DDNSUpdateError(Exception):
    """Exception raised for errors during DDNS update."""


class DDNSAgentv6(object):
    """
    DDNS Updater with IPv6
    """

    @classmethod
    def my_ipv6_address(cls) -> str:
        """
        Retrieve the IPv6 address of the current machine.

        Returns:
            str: IPv6 address of the current machine.

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
    def do_dns_update(
        cls, cf: CloudFlare.CloudFlare, zone_id: str, dns_name: str, ip_address: str
    ) -> None:
        """
        Update DNS records with the specified IPv6 address.

        Args:
            cf (CloudFlare.CloudFlare): Cloudflare client.
            zone_id (str): Zone identifier.
            dns_name (str): DNS name to update.
            ip_address (str): IPv6 address to set.

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

        # no exsiting dns record to update - so create dns record
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
                exit("Error: Record was not created")
        except CloudFlareAPIError as e:
            exit(
                "Error: /zones.dns_records.post %s - %d %s - api call failed"
                % (dns_name, e, e)
            )
        print("CREATED: %s %s" % (dns_name, ip_address))

    def __call__(self) -> None:
        """
        Perform DNS update for all specified hosts.
        """
        ip_address = self.my_ipv6_address()
        print("MY IP: %s" % (ip_address))

        dns_names: list[str] = []
        with open("./ddns.hosts") as file:
            for line in file:
                test = line.strip()
                if len(test) != 0 and validators.domain(test):
                    dns_names.append(test)

        if len(dns_names) == 0:
            exit("Error: No DDNS Host specified or set to a proper FQDN")

        print("HOSTS TO UPDATE: %s" % (dns_names))

        zone_name = ".".join(dns_names[0].split(".")[-2:])

        token = os.getenv("CLOUDFLARE_API_TOKEN")
        if token is not None:
            print("CLOUDFLARE_API_TOKEN: type: %s ;length: %d" % (type(token), len(token)))
        else:
            print("CLOUDFLARE_API_TOKEN: type: %s ;" % (type(token)))

        cf = CloudFlare.CloudFlare(token=token)

        # grab the zone identifier
        try:
            params = {"name": zone_name}
            zones = cf.zones.get(params=params)
        except CloudFlareAPIError as e:
            exit("Error: /zones %d %s - api call failed" % (e, e))
        except Exception as e:
            exit("Error: /zones.get - %s - api call failed" % (e))

        if len(zones) == 0:
            exit("Error: /zones.get - %s - zone not found" % (zone_name))

        if len(zones) != 1:
            exit(
                "Error: /zones.get - %s - api call returned %d items"
                % (zone_name, len(zones))
            )

        zone_id = zones[0]["id"]

        error: list[str] = []
        for dns in dns_names:
            try:
                self.do_dns_update(cf, zone_id, dns, ip_address)
            except DDNSUpdateError as e:
                error.append("Error Updating %s: %s" % (e))

        if len(error) != 0:
            print(
                json.dumps(error, indent=4),
                file=sys.stderr,
            )
            exit(1)


if __name__ == "__main__":
    agent = DDNSAgentv6()
    agent()

#!/usr/bin/env python

import json
import os
# import sys

import CloudFlare
import requests
import validators
from CloudFlare.exceptions import CloudFlareAPIError
from dotenv import load_dotenv

# sys.path.insert(0, os.path.abspath('..'))

load_dotenv()


class DDNSAgentv6(object):
    """
    DDNS Updater with IPv6
    """
    @classmethod
    def my_ipv6_address(cls) -> str:
        ip_finders = [
            'https://api6.ipify.org/',
            'https://www.trackip.net/ip',
            'https://ipapi.co/ip'
        ]
        ip_address = str()
        err_outputs = list()
        for url in ip_finders:
            try:
                ip_address = requests.get(url).text
            except Exception as e:
                err_outputs.append(
                    {'api': url, 'output': str(e)})
                continue

            if validators.ipv6(ip_address):  # type: ignore
                break

            err_outputs.append({'api': url, 'output': ip_address})

        if not validators.ipv6(ip_address):  # type: ignore
            exit("Error: Could not find ipv6 address" +
                 json.dumps(err_outputs, indent=4))

        return ip_address

    @classmethod
    def do_dns_update(cls, cf: CloudFlare.CloudFlare, zone_id: str, dns_name: str, ip_address: str) -> None:
        try:
            params = {'name': dns_name, 'match': 'all',
                      'type': 'AAAA'}
            dns_records = cf.zones.dns_records.get(zone_id, params=params)
        except CloudFlareAPIError as e:
            exit('Error: /zones/dns_records %s - %d %s - api call failed' %
                 (dns_name, e, e))

        updated = False

        # update the record - unless it's already correct
        for dns_record in dns_records:
            old_ip_address = dns_record['content']

            if ip_address == old_ip_address:
                print('UNCHANGED: %s %s' % (dns_name, ip_address))
                updated = True
                continue

            proxied_state = dns_record['proxied']

            # Yes, we need to update this record
            dns_record_id = dns_record['id']
            dns_record = {
                'name': dns_name,
                'type': 'AAAA',
                'content': ip_address,
                'proxied': proxied_state
            }
            try:
                dns_record = cf.zones.dns_records.put(
                    zone_id, dns_record_id, data=dns_record)
                params = {'name': dns_name, 'match': 'all',
                          'type': 'AAAA'}
                dns_records = cf.zones.dns_records.get(zone_id, params=params)
                if dns_records[0]['content'] == ip_address:
                    updated = True
                else:
                    exit("Error: Record was not updated")
            except CloudFlareAPIError as e:
                exit('Error: /zones.dns_records.put %s - %d %s - api call failed' %
                     (dns_name, e, e))
            print('UPDATED: %s %s -> %s' %
                  (dns_name, old_ip_address, ip_address))

        if updated:
            return

        # no exsiting dns record to update - so create dns record
        dns_record = {
            'name': dns_name,
            'type': 'AAAA',
            'content': ip_address,
            'ttl': 60
        }
        try:
            dns_record = cf.zones.dns_records.post(zone_id, data=dns_record)
            params = {'name': dns_name, 'match': 'all',
                      'type': 'AAAA'}
            dns_records = cf.zones.dns_records.get(zone_id, params=params)
            if dns_records[0]['content'] != ip_address:
                exit("Error: Record was not created")
        except CloudFlareAPIError as e:
            exit('Error: /zones.dns_records.post %s - %d %s - api call failed' %
                 (dns_name, e, e))
        print('CREATED: %s %s' % (dns_name, ip_address))

    def __call__(self) -> None:
        dns_name = os.getenv("DDNS_HOST")
        if dns_name is None or not validators.domain(dns_name):  # type: ignore
            exit("Error: DDNS_HOST not set to a proper FQDN")

        zone_name = '.'.join(dns_name.split('.')[-2:])

        ip_address = self.my_ipv6_address()

        print('MY IP: %s %s' % (dns_name, ip_address))

        cf = CloudFlare.CloudFlare()

        # grab the zone identifier
        try:
            params = {'name': zone_name}
            zones = cf.zones.get(params=params)
        except CloudFlareAPIError as e:
            exit('Error: /zones %d %s - api call failed' % (e, e))
        except Exception as e:
            exit('Error: /zones.get - %s - api call failed' % (e))

        if len(zones) == 0:
            exit('Error: /zones.get - %s - zone not found' % (zone_name))

        if len(zones) != 1:
            exit('Error: /zones.get - %s - api call returned %d items' %
                 (zone_name, len(zones)))

        zone_id = zones[0]['id']

        self.do_dns_update(cf, zone_id, dns_name, ip_address)


if __name__ == '__main__':
    agent = DDNSAgentv6()
    agent()

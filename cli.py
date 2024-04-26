"""
Dave4272's Admin Tools
"""
from tools.manage.machineidgenerator import MachineIDGenerator
from tools.ddns.agent import DDNSAgentv6
from tools.rpi.config import ConfigGenerator

if __name__ == "__main__":
    agent = ConfigGenerator(8, "mac.corpdk.com", "rpi4")
    agent(2, "./input/values.yml", "output")
    pass
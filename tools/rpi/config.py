import os

from dotenv import load_dotenv

from tools.jinja.renderer import JinjaTemplateRenderer
from tools.manage.machineidgenerator import MachineIDGenerator

load_dotenv()


class ConfigGenerator(object):
    """Config Generator"""

    def __init__(self, random_length: int) -> None:
        self.random_length = random_length

    def __call__(
        self, number_of_devices: int, input_file: str, output_path: str = "output"
    ) -> None:
        for i in range(1, number_of_devices + 1):
            output_dir = os.path.join(
                output_path, f"device-{i:0{len(str(number_of_devices)) + 1}d}"
            )
            midgen = MachineIDGenerator(self.random_length)
            midgen(output_dir)
            values = {"machine_id": midgen.machine_id, "ddns_host": midgen.ddns_host}
            jinjarender = JinjaTemplateRenderer(
                "./tools/rpi/templates/", output_dir, values
            )
            jinjarender.load_yaml_data(input_file)
            jinjarender()
        pass


if __name__ == "__main__":
    agent = ConfigGenerator(8)
    agent(2, "./input/values.yml", "output")

#!/usr/bin/env python
"""
Jinja Template Renderer

This module defines a class, JinjaTemplateRenderer, for rendering Jinja templates
with YAML data while replacing environment variables.

Usage:
1. Initialize an instance of JinjaTemplateRenderer with the desired parameters.
2. Load YAML data using the load_yaml_data method.
3. Call the instance to render templates with loaded YAML data and write the output to files.

Example:
    renderer = JinjaTemplateRenderer(templates_directory='my_templates', output_directory='my_output')
    renderer.load_yaml_data('data.yaml')
    renderer()

Classes:
    JinjaTemplateRenderer:
        A class to render Jinja templates with YAML data, replacing environment variables.

        Methods:
            render_template(template_path: str) -> str:
                Renders a Jinja template file.
            
            replace_env_variables(data: Union[str, dict, list]) -> Union[str, dict, list]:
                Recursively replaces environment variables in data.
            
            load_yaml_data(yaml_file: str) -> None:
                Loads YAML data from a file.
            
            __call__() -> None:
                Renders templates with loaded YAML data and writes the output to files.
"""

import os
import re
from typing import Optional, Union

import yaml
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

load_dotenv()


class JinjaTemplateRenderer(object):
    """
    Class to render Jinja templates with YAML data, replacing environment variables.

    Args:
        templates_directory (str): The directory containing the Jinja templates.
        output_directory (str): The directory where the rendered templates will be saved.
        env_vars (dict, optional): A dictionary containing environment variables.
            Keys are the lowercase names of the environment variables.

    Methods:
        render_template(template_path: str) -> str:
            Renders a Jinja template file.

        replace_env_variables(data: Union[str, dict, list]) -> Union[str, dict, list]:
            Recursively replaces environment variables in data.

        load_yaml_data(yaml_file: str) -> None:
            Loads YAML data from a file.

        __call__() -> None:
            Renders templates with loaded YAML data and writes the output to files.
    """

    def __init__(
        self,
        templates_directory: str = "templates",
        output_directory: str = "output",
        env_vars: Optional[dict] = None,
    ) -> None:
        self.templates_directory: str = templates_directory
        self.output_directory: str = output_directory
        self.env: Environment = Environment(
            loader=FileSystemLoader(self.templates_directory)
        )
        self.yaml_data: Optional[Union[str, dict, list]] = None
        self.env_vars: dict = env_vars or {}

    def render_template(self, template_path: str) -> str:
        """
        Renders a Jinja template file.

        Args:
            template_path (str): The path to the Jinja template file.

        Returns:
            str: The rendered template content.
        """
        template = self.env.get_template(os.path.basename(template_path))
        return template.render(self.yaml_data)

    def replace_env_variables(
        self, data: Union[str, dict, list]
    ) -> Union[str, dict, list]:
        """
        Recursively replaces environment variables in data.

        Args:
            data (Union[str, dict, list]): The data to process.

        Returns:
            Union[str, dict, list]: The processed data with environment variables replaced.
        """
        if isinstance(data, str):
            # Replace environment variables
            env_var_pattern = r"\${([^\${}]*)}"
            matches = re.findall(env_var_pattern, data)
            for match in matches:
                # Try to get the value from the provided dictionary first
                env_variable = self.env_vars.get(match.lower())
                if env_variable is None:
                    # If not found, try to get it from the actual environment
                    env_variable = os.getenv(match)
                if env_variable:
                    data = data.replace(f"${{{match}}}", env_variable)
            return data
        elif isinstance(data, dict):
            # Recursively replace environment variables in nested dictionaries
            for key, value in data.items():
                data[key] = self.replace_env_variables(value)
            return data
        elif isinstance(data, list):
            # Recursively replace environment variables in nested lists
            return [self.replace_env_variables(item) for item in data]
        else:
            return data

    def load_yaml_data(self, yaml_file: str) -> None:
        """
        Loads YAML data from a file.

        Args:
            yaml_file (str): The path to the YAML file.
        """
        with open(yaml_file, "r") as file:
            self.yaml_data = yaml.safe_load(file)

    def __call__(self) -> None:
        """
        Renders templates with loaded YAML data and writes the output to files.
        """
        # Replace environment variables in YAML data
        if self.yaml_data is not None:
            self.yaml_data = self.replace_env_variables(self.yaml_data)

        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_directory):
            os.makedirs(self.output_directory)

        # Render and write templates
        for filename in os.listdir(self.templates_directory):
            if filename.endswith(".j2"):
                template_path = os.path.join(self.templates_directory, filename)
                output_filename = filename.replace(".j2", "")
                output_path = os.path.join(self.output_directory, output_filename)

                # Render template with YAML data
                rendered_template = self.render_template(template_path)

                # Write rendered template to file
                with open(output_path, "w") as output_file:
                    output_file.write(rendered_template)


# Example usage:
if __name__ == "__main__":
    renderer = JinjaTemplateRenderer(
        templates_directory="my_templates", output_directory="my_output"
    )
    renderer.load_yaml_data("data.yaml")
    renderer()  # Now the instance is callable, invoking the __call__() method

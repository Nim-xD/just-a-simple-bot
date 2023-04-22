import discord
from discord.ext import commands

# Will be right back


class SlashCommand(commands.Command):
    def __init__(self, func, **kwargs):
        super().__init__(func, **kwargs)
        self.slash: bool = False

    def _parse_slash_payload(self):
        if self.slash is False:
            return

        payload = {
            "name": self.name,
            "description": self.short_doc or self.brief,
            "options": [],
        }

        for name, param in self.clean_params.items():
            option = {
                "name": name,
                "required": param.default is param.empty
                and not self._is_typing_optional(param.annotation if param.annotation is not param.empty else str),
            }
            payload["options"].append(option)

        return payload


def slash_command(*args, **kwargs):
    return commands.command(*args, **kwargs, cls=SlashCommand)

from __future__ import annotations

from typing import Dict, List, Optional
import discord
import models


class PrefixManager:
    def __init__(self):
        self._cached: Dict[Optional[int], List[str]] = {}

    async def get_prefixes(self, guild: Optional[discord.Guild] = None) -> List[str]:
        ret: List[str]

        gid: Optional[int] = guild.id or None

        if gid in self._cached:
            ret = self._cached[gid].copy()

        elif gid is not None:
            _guild_model: Optional[models.Guild] = await models.Guild.get_or_none(id=guild.id)

            ret = ["p!", "P!"] if _guild_model is None else list(_guild_model.prefix)
            self._cached[gid] = ret.copy()

        return ret

    async def set_prefixes(self):
        ...

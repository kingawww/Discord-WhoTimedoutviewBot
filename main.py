import os
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from aiohttp import web

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set")


# =========================
# Discord Bot
# =========================

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Slash command sync error: {e}")


@bot.tree.command(
    name="timeoutmemberslist",
    description="現在タイムアウトされているメンバーの一覧を表示します"
)
@discord.app_commands.default_permissions(moderate_members=True)
@discord.app_commands.checks.has_permissions(moderate_members=True)
async def timeoutmemberslist(
    interaction: discord.Interaction
):
    await interaction.response.defer()

    guild = interaction.guild

    if guild is None:
        await interaction.followup.send(
            "このコマンドはサーバー内でのみ使用できます。"
        )
        return

    # メンバー一覧を取得
    members = guild.members

    now = datetime.now(timezone.utc)

    timeout_members = []

    for member in members:
        # communication_disabled_until が
        # 現在時刻より後ならタイムアウト中
        timeout_until = member.communication_disabled_until

        if timeout_until is not None and timeout_until > now:
            timeout_members.append(
                (member, timeout_until)
            )

    # タイムアウト中のメンバーがいない場合
    if not timeout_members:
        await interaction.followup.send(
            "現在タイムアウトされているメンバーはいません。"
        )
        return

    # 見やすいようにユーザー名順
    timeout_members.sort(
        key=lambda x: x[0].display_name.lower()
    )

    lines = []

    for member, timeout_until in timeout_members:
        timestamp = int(timeout_until.timestamp())

        # mention はスマホからタップ可能
        line = (
            f"• {member.display_name} "
            f"({member.mention}) "
            f"・解除 <t:{timestamp}:R>"
        )

        lines.append(line)

    # Discordのメッセージ上限を考慮して分割
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 > 1900:
            chunks.append(current)
            current = line
        else:
            if current:
                current += "\n"
            current += line

    if current:
        chunks.append(current)

    # 最初のメッセージ
    total = len(timeout_members)

    await interaction.followup.send(
        f"🔇 **現在タイムアウト中のメンバー: {total}人**\n\n"
        + chunks[0]
    )

    # 残り
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


# 権限エラー
@timeoutmemberslist.error
async def timeoutmemberslist_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError
):
    if isinstance(
        error,
        discord.app_commands.errors.MissingPermissions
    ):
        message = "❌ このコマンドを使用するには **メンバーをタイムアウト** 権限が必要です。"

    else:
        print(f"Command error: {error}")
        message = "❌ コマンドの実行中にエラーが発生しました。"

    if interaction.response.is_done():
        await interaction.followup.send(message)
    else:
        await interaction.response.send_message(message)


# =========================
# Render用 HTTP Server
# =========================

async def health(request):
    return web.Response(
        text="Discord bot is running!"
    )


async def start_web_server():
    app = web.Application()

    app.router.add_get("/", health)

    port = int(os.environ.get("PORT", 10000))

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=port
    )

    await site.start()

    print(f"HTTP server running on port {port}")


# =========================
# 起動
# =========================

async def main():
    await start_web_server()

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

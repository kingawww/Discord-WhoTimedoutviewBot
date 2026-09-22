import os
import asyncio
import traceback
from datetime import datetime, timezone

import discord
from discord.ext import commands

from aiohttp import web


# =========================
# Environment
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
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


# =========================
# 共通設定
# =========================

# Discordの2000文字制限より余裕を持たせる
MAX_MESSAGE_LENGTH = 1900


# =========================
# メンバー取得
# =========================

async def fetch_all_members(guild: discord.Guild):

    members = []

    async for member in guild.fetch_members(limit=None):
        members.append(member)

    return members


# =========================
# 長いメッセージを分割
# =========================

def split_message(lines, max_length=MAX_MESSAGE_LENGTH):

    chunks = []
    current = ""

    for line in lines:

        # 1行そのものが長すぎる場合
        if len(line) > max_length:

            if current:
                chunks.append(current)
                current = ""

            # 1行をさらに分割
            for i in range(0, len(line), max_length):
                chunks.append(line[i:i + max_length])

            continue

        if current and len(current) + len(line) + 1 > max_length:

            chunks.append(current)
            current = line

        else:

            if current:
                current += "\n"

            current += line

    if current:
        chunks.append(current)

    return chunks


# =========================
# 2000文字超過確認View
# =========================

class OutputConfirmView(discord.ui.View):

    def __init__(self, author_id: int, chunks):

        super().__init__(timeout=180)

        self.author_id = author_id
        self.chunks = chunks
        self.finished = False

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ):

        if interaction.user.id != self.author_id:

            await interaction.response.send_message(
                "❌ このボタンはコマンドを実行した本人のみ使用できます。",
                ephemeral=True
            )

            return False

        return True

    @discord.ui.button(
        label="全員出力",
        style=discord.ButtonStyle.green
    )
    async def output_all(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.finished:
            return

        self.finished = True

        await interaction.response.edit_message(
            content="📤 全員分を出力しています……",
            view=None
        )

        for index, chunk in enumerate(self.chunks):

            try:

                await interaction.followup.send(chunk)

            except Exception:

                print(
                    f"Error while sending chunk {index + 1}:"
                )

                traceback.print_exc()

                break

        self.stop()

    @discord.ui.button(
        label="ここで止める",
        style=discord.ButtonStyle.red
    )
    async def stop_output(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.finished:
            return

        self.finished = True

        await interaction.response.edit_message(
            content="⏹️ 出力を中止しました。",
            view=None
        )

        self.stop()

    async def on_timeout(self):

        if not self.finished:
            self.finished = True

            self.stop()


# =========================
# 大量メンバー出力
# =========================

async def send_member_list(
    interaction: discord.Interaction,
    title: str,
    lines: list[str]
):

    chunks = split_message(lines)

    if not chunks:
        await interaction.followup.send(
            f"{title}\n\nメンバーはいません。"
        )
        return

    # 1メッセージで収まる場合
    if len(chunks) == 1:

        await interaction.followup.send(
            f"{title}\n\n{chunks[0]}"
        )

        return

    # 2000文字を超える場合
    view = OutputConfirmView(
        interaction.user.id,
        chunks
    )

    await interaction.followup.send(
        f"{title}\n\n"
        f"⚠️ メンバーが多いため、全員分を出力すると "
        f"{len(chunks)}個のメッセージに分かれます。\n\n"
        f"全員を出力しますか？",
        view=view
    )


# =========================
# Bot Ready
# =========================

@bot.event
async def on_ready():

    print(
        f"Logged in as {bot.user} ({bot.user.id})"
    )

    try:

        synced = await bot.tree.sync()

        print(
            f"Synced {len(synced)} slash command(s)"
        )

    except Exception:

        print("Slash command sync error:")
        traceback.print_exc()


# =========================
# /timeoutmemberslist
# =========================

@bot.tree.command(
    name="timeoutmemberslist",
    description="現在タイムアウトされているメンバーの一覧を表示します"
)
@discord.app_commands.default_permissions(
    moderate_members=True
)
@discord.app_commands.checks.has_permissions(
    moderate_members=True
)
async def timeoutmemberslist(
    interaction: discord.Interaction
):

    try:

        await interaction.response.defer()

        guild = interaction.guild

        if guild is None:

            await interaction.followup.send(
                "このコマンドはサーバー内でのみ使用できます。"
            )

            return

        members = await fetch_all_members(guild)

        print(
            f"Checking timeout members in {guild.name}: "
            f"{len(members)} members"
        )

        now = datetime.now(timezone.utc)

        timeout_members = []

        for member in members:

            timeout_until = member.timed_out_until

            if (
                timeout_until is not None
                and timeout_until > now
            ):

                timeout_members.append(
                    (member, timeout_until)
                )

        if not timeout_members:

            await interaction.followup.send(
                "現在タイムアウトされているメンバーはいません。"
            )

            return

        timeout_members.sort(
            key=lambda x: x[0].display_name.lower()
        )

        lines = []

        for member, timeout_until in timeout_members:

            timestamp = int(
                timeout_until.timestamp()
            )

            line = (
                f"• {member.mention} "
                f"・解除 <t:{timestamp}:R>"
            )

            lines.append(line)

        chunks = split_message(lines)

        total = len(timeout_members)

        await interaction.followup.send(
            f"🔇 **現在タイムアウト中のメンバー: {total}人**\n\n"
            + chunks[0]
        )

        for chunk in chunks[1:]:

            await interaction.followup.send(
                chunk
            )

    except Exception:

        print(
            "Error in /timeoutmemberslist:"
        )

        traceback.print_exc()

        if interaction.response.is_done():

            await interaction.followup.send(
                "❌ コマンドの実行中にエラーが発生しました。"
            )

        else:

            await interaction.response.send_message(
                "❌ コマンドの実行中にエラーが発生しました。"
            )


# =========================
# /allmemberlistup
# =========================

@bot.tree.command(
    name="allmemberlistup",
    description="サーバーの全メンバーをロール順に一覧表示します"
)
async def allmemberlistup(
    interaction: discord.Interaction
):

    try:

        await interaction.response.defer()

        guild = interaction.guild

        if guild is None:

            await interaction.followup.send(
                "このコマンドはサーバー内でのみ使用できます。"
            )

            return

        # =========================
        # 全メンバー取得
        # =========================

        members = await fetch_all_members(guild)

        print(
            f"All member list requested in {guild.name}: "
            f"{len(members)} members"
        )

        # =========================
        # メンバーをIDで管理
        # =========================

        member_map = {
            member.id: member
            for member in members
        }

        # =========================
        # ロールを上位から並べる
        # =========================

        roles = [
            role
            for role in guild.roles
            if not role.is_default()
        ]

        roles.sort(
            key=lambda role: role.position,
            reverse=True
        )

        lines = []

        # =========================
        # ロール別に出力
        # =========================

        assigned_member_ids = set()

        for role in roles:

            role_members = [
                member
                for member in members
                if role in member.roles
            ]

            if not role_members:
                continue

            role_members.sort(
                key=lambda member: (
                    member.display_name.lower(),
                    member.id
                )
            )

            lines.append(
                f"【{role.name}】"
            )

            for member in role_members:

                lines.append(
                    member.mention
                )

                assigned_member_ids.add(
                    member.id
                )

            lines.append("")

        # =========================
        # ロールを持っていない人
        # =========================

        no_role_members = [
            member
            for member in members
            if member.id not in assigned_member_ids
        ]

        if no_role_members:

            no_role_members.sort(
                key=lambda member: (
                    member.display_name.lower(),
                    member.id
                )
            )

            lines.append(
                "【ロールなし】"
            )

            for member in no_role_members:

                lines.append(
                    member.mention
                )

        # =========================
        # 出力
        # =========================

        await send_member_list(
            interaction,
            "📋 **All Member List 👇**",
            lines
        )

    except Exception:

        print(
            "Error in /allmemberlistup:"
        )

        traceback.print_exc()

        if interaction.response.is_done():

            await interaction.followup.send(
                "❌ 全メンバー一覧の取得中にエラーが発生しました。"
            )

        else:

            await interaction.response.send_message(
                "❌ 全メンバー一覧の取得中にエラーが発生しました。"
            )


# =========================
# ロール選択View
# =========================

class RoleListView(discord.ui.View):

    def __init__(
        self,
        author_id: int,
        roles: list[discord.Role],
        members: list[discord.Member]
    ):

        super().__init__(timeout=180)

        self.author_id = author_id
        self.roles = roles
        self.members = members

        self.page = 0
        self.per_page = 20

        self.update_buttons()

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ):

        if interaction.user.id != self.author_id:

            await interaction.response.send_message(
                "❌ このボタンはコマンドを実行した本人のみ使用できます。",
                ephemeral=True
            )

            return False

        return True

    def update_buttons(self):

        self.clear_items()

        start = self.page * self.per_page

        end = start + self.per_page

        page_roles = self.roles[start:end]

        for role in page_roles:

            label = role.name

            if len(label) > 80:
                label = label[:77] + "..."

            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary
            )

            async def callback(
                interaction: discord.Interaction,
                selected_role=role
            ):

                await self.show_role(
                    interaction,
                    selected_role
                )

            button.callback = callback

            self.add_item(button)

        # ページ操作
        if len(self.roles) > self.per_page:

            previous_button = discord.ui.Button(
                label="◀ 前へ",
                style=discord.ButtonStyle.primary,
                disabled=(self.page == 0)
            )

            async def previous_callback(
                interaction: discord.Interaction
            ):

                self.page -= 1

                self.update_buttons()

                await interaction.response.edit_message(
                    content=self.page_text(),
                    view=self
                )

            previous_button.callback = previous_callback

            next_button = discord.ui.Button(
                label="次へ ▶",
                style=discord.ButtonStyle.primary,
                disabled=(
                    (self.page + 1)
                    * self.per_page
                    >= len(self.roles)
                )
            )

            async def next_callback(
                interaction: discord.Interaction
            ):

                self.page += 1

                self.update_buttons()

                await interaction.response.edit_message(
                    content=self.page_text(),
                    view=self
                )

            next_button.callback = next_callback

            self.add_item(previous_button)
            self.add_item(next_button)

    def page_text(self):

        total_pages = (
            (len(self.roles) + self.per_page - 1)
            // self.per_page
        )

        return (
            "📋 **表示するロールを選択してください。**\n\n"
            f"ページ {self.page + 1}/{total_pages}"
        )

    async def show_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role
    ):

        role_members = [
            member
            for member in self.members
            if role in member.roles
        ]

        role_members.sort(
            key=lambda member: (
                member.display_name.lower(),
                member.id
            )
        )

        lines = [
            f"【{role.name}】"
        ]

        for member in role_members:

            lines.append(
                member.mention
            )

        chunks = split_message(lines)

        self.stop()

        # メンバーなし
        if len(role_members) == 0:

            await interaction.response.edit_message(
                content=(
                    f"【{role.name}】\n\n"
                    "このロールを持っているメンバーはいません。"
                ),
                view=None
            )

            return

        # 1メッセージで収まる
        if len(chunks) == 1:

            await interaction.response.edit_message(
                content=chunks[0],
                view=None
            )

            return

        # 2000文字超過
        view = OutputConfirmView(
            interaction.user.id,
            chunks
        )

        await interaction.response.edit_message(
            content=(
                f"【{role.name}】\n\n"
                f"⚠️ このロールには "
                f"{len(role_members)}人います。\n"
                f"全員出力すると "
                f"{len(chunks)}個のメッセージに分かれます。\n\n"
                f"全員を出力しますか？"
            ),
            view=view
        )

    async def on_timeout(self):

        self.stop()


# =========================
# /rolelistup
# =========================

@bot.tree.command(
    name="rolelistup",
    description="ロールを選択して、そのロールのメンバー一覧を表示します"
)
async def rolelistup(
    interaction: discord.Interaction
):

    try:

        await interaction.response.defer()

        guild = interaction.guild

        if guild is None:

            await interaction.followup.send(
                "このコマンドはサーバー内でのみ使用できます。"
            )

            return

        # =========================
        # 全メンバー取得
        # =========================

        members = await fetch_all_members(guild)

        print(
            f"Role list requested in {guild.name}: "
            f"{len(members)} members"
        )

        # =========================
        # ロールを上位から並べる
        # =========================

        roles = [
            role
            for role in guild.roles
            if not role.is_default()
        ]

        roles.sort(
            key=lambda role: role.position,
            reverse=True
        )

        # メンバーが1人もいないロールは
        # 選択肢から除外
        roles = [
            role
            for role in roles
            if any(
                role in member.roles
                for member in members
            )
        ]

        if not roles:

            await interaction.followup.send(
                "このサーバーにはメンバーが所属しているロールがありません。"
            )

            return

        # =========================
        # ロール選択画面
        # =========================

        view = RoleListView(
            interaction.user.id,
            roles,
            members
        )

        await interaction.followup.send(
            view.page_text(),
            view=view
        )

    except Exception:

        print(
            "Error in /rolelistup:"
        )

        traceback.print_exc()

        if interaction.response.is_done():

            await interaction.followup.send(
                "❌ ロール一覧の取得中にエラーが発生しました。"
            )

        else:

            await interaction.response.send_message(
                "❌ ロール一覧の取得中にエラーが発生しました。"
            )


# =========================
# Command Error Handler
# =========================

@timeoutmemberslist.error
async def timeoutmemberslist_error(
    interaction: discord.Interaction,
    error
):

    print(
        "Slash command permission/error:"
    )

    traceback.print_exception(
        type(error),
        error,
        error.__traceback__
    )

    if isinstance(
        error,
        discord.app_commands.errors.MissingPermissions
    ):

        message = (
            "❌ このコマンドを使用するには "
            "**メンバーをタイムアウト** 権限が必要です。"
        )

    else:

        message = (
            "❌ コマンドの実行中にエラーが発生しました。"
        )

    if interaction.response.is_done():

        await interaction.followup.send(
            message
        )

    else:

        await interaction.response.send_message(
            message
        )


# =========================
# Render HTTP Server
# =========================

async def health(request):

    return web.Response(
        text="Discord bot is running!"
    )


async def start_web_server():

    app = web.Application()

    app.router.add_get(
        "/",
        health
    )

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=port
    )

    await site.start()

    print(
        f"HTTP server running on port {port}"
    )


# =========================
# Main
# =========================

async def main():

    await start_web_server()

    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":

    asyncio.run(main())

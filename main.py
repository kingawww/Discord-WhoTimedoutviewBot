import os
import random
import asyncio
import traceback
from datetime import datetime, timezone

import discord
from discord.ext import commands

from aiohttp import web

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set")

MAX_MESSAGE_LENGTH = 1900

# =========================
# Embed Color Settings
# =========================

# Bot全体で共有されるEmbedカラー
EMBED_COLOR = discord.Color.green()

# Bot開発者本人のDiscord User ID
# ↓ここを自分のDiscord User IDに変更してください
DEVELOPER_ID = os.getenv("DEVELOPER_ID")

if not DEVELOPER_ID:
    raise RuntimeError("DEVELOPER_ID environment variable is not set")

DEVELOPER_ID = int(DEVELOPER_ID)

# ランダムEmbedカラーイベントが開催中か
RANDOM_COLOR_EVENT = False

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


def is_developer(interaction: discord.Interaction):
    return interaction.user.id == DEVELOPER_ID


COLOR_CHOICES = [
    discord.app_commands.Choice(name="□ Default", value="57F287"),
    discord.app_commands.Choice(name="🔴 Red", value="FF0000"),
    discord.app_commands.Choice(name="🟠 Orange", value="FF8000"),
    discord.app_commands.Choice(name="🟡 Yellow", value="FFFF00"),
    discord.app_commands.Choice(name="🟢 Green", value="00FF00"),
    discord.app_commands.Choice(name="🔵 Cyan", value="00FFFF"),
    discord.app_commands.Choice(name="🔷 Blue", value="0080FF"),
    discord.app_commands.Choice(name="🟣 Purple", value="8000FF"),
    discord.app_commands.Choice(name="🩷 Pink", value="FF00AA"),
    discord.app_commands.Choice(name="🟤 Brown", value="8B4513"),
    discord.app_commands.Choice(name="⚫ Black", value="000000"),
    discord.app_commands.Choice(name="⚪ White", value="FFFFFF"),
    discord.app_commands.Choice(name="🌸 Rose", value="FF4F81"),
    discord.app_commands.Choice(name="🌊 Deep Blue", value="0047AB"),
    discord.app_commands.Choice(name="🍷 Burgundy", value="800020"),
    discord.app_commands.Choice(name="🌌 Dark Purple", value="301934"),
]


@bot.tree.command(
    name="changeembedcolor",
    description="(DEV)BotのEmbedカラーを変更します"
)
@discord.app_commands.describe(
    color="変更するEmbedカラー"
)
@discord.app_commands.choices(
    color=COLOR_CHOICES
)
async def changeembedcolor(
    interaction: discord.Interaction,
    color: discord.app_commands.Choice[str]
):
    if not is_developer(interaction):
        await interaction.response.send_message(
            "❌ このコマンドはBot開発者のみ使用できます。",
            ephemeral=True
        )
        return

    global EMBED_COLOR

    EMBED_COLOR = discord.Color(int(color.value, 16))

    await interaction.response.send_message(
        f"🎨 Embed color changed to **{color.name}**."
    )


@bot.tree.command(
    name="truerandomembedcolorevent",
    description="(DEV)ランダムEmbedカラーイベントを開始します"
)
async def truerandomembedcolorevent(
    interaction: discord.Interaction
):
    if not is_developer(interaction):
        await interaction.response.send_message(
            "❌ このコマンドはBot開発者のみ使用できます。",
            ephemeral=True
        )
        return

    global RANDOM_COLOR_EVENT

    RANDOM_COLOR_EVENT = True

    await interaction.response.send_message(
        "started now!!"
    )


@bot.tree.command(
    name="falserandomembedcolorevent",
    description="(DEV)ランダムEmbedカラーイベントを終了します"
)
async def falserandomembedcolorevent(
    interaction: discord.Interaction
):
    if not is_developer(interaction):
        await interaction.response.send_message(
            "❌ このコマンドはBot開発者のみ使用できます。",
            ephemeral=True
        )
        return

    global RANDOM_COLOR_EVENT

    RANDOM_COLOR_EVENT = False

    await interaction.response.send_message(
        "ended now."
    )


@bot.tree.command(
    name="serverembedrandomcolor",
    description="Embedカラーをランダムに変更します"
)
async def serverembedrandomcolor(
    interaction: discord.Interaction
):
    if not RANDOM_COLOR_EVENT:
        await interaction.response.send_message(
            "❌ Random Embed Color Event is not active.",
            ephemeral=True
        )
        return

    global EMBED_COLOR

    random_value = random.randint(0x000000, 0xFFFFFF)
    EMBED_COLOR = discord.Color(random_value)

    await interaction.response.send_message(
        "🎨 Embed color changed randomly!"
    )


def create_embed(title: str, description: str):
    return discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR
    )


def split_message(lines, max_length=MAX_MESSAGE_LENGTH):
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 > max_length:
            if current:
                chunks.append(current)
            current = line
        else:
            if current:
                current += "\n"
            current += line

    if current:
        chunks.append(current)

    return chunks


async def fetch_all_members(guild: discord.Guild):
    members = []

    async for member in guild.fetch_members(limit=None):
        members.append(member)

    return members


class OutputConfirmView(discord.ui.View):
    def __init__(self, interaction, chunks, title):
        super().__init__(timeout=120)
        self.author_id = interaction.user.id
        self.chunks = chunks
        self.title = title
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ このボタンはコマンドを実行した本人のみ使用できます。",
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(
        label="全員出力",
        style=discord.ButtonStyle.success
    )
    async def output_all(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if self.finished:
            await interaction.response.send_message(
                "この操作はすでに終了しています。",
                ephemeral=True
            )
            return

        self.finished = True

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            embed=create_embed(
                "📤 全員分を出力しています……",
                "少し待ってください。"
            ),
            view=self
        )

        for index, chunk in enumerate(self.chunks):
            # メンバーのメンションは通常の本文として送信し、
            # Discord上でタップできる状態を維持する。
            await interaction.followup.send(
                content=chunk
            )

    @discord.ui.button(
        label="ここで止める",
        style=discord.ButtonStyle.secondary
    )
    async def stop_output(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if self.finished:
            await interaction.response.send_message(
                "この操作はすでに終了しています。",
                ephemeral=True
            )
            return

        self.finished = True

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            embed=create_embed(
                "⏹️ 出力を停止しました",
                "ここまでの確認で終了します。"
            ),
            view=self
        )


async def send_member_list(
    interaction: discord.Interaction,
    lines,
    title="📋 Member List 👇"
):
    chunks = split_message(lines)

    if not chunks:
        await interaction.followup.send(
            embed=create_embed(
                title,
                "該当するメンバーはいません。"
            )
        )
        return

    # メンバーのメンション部分はEmbedに入れず、
    # 通常のメッセージ本文として送信することでタップ可能にする。
    if len(chunks) == 1:
        await interaction.followup.send(
            content=chunks[0]
        )
        return

    view = OutputConfirmView(
        interaction,
        chunks,
        title
    )

    await interaction.followup.send(
        embed=create_embed(
            "📋 出力確認",
            f"出力が **{len(chunks)}個** に分かれます。\n"
            "全員分を出力しますか？"
        ),
        view=view
    )


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception:
        print("Slash command sync error:")
        traceback.print_exc()


@bot.tree.command(
    name="timeoutmemberslist",
    description="現在タイムアウトされているメンバーの一覧を表示します"
)
@discord.app_commands.default_permissions(moderate_members=True)
@discord.app_commands.checks.has_permissions(moderate_members=True)
async def timeoutmemberslist(interaction: discord.Interaction):
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

            if timeout_until is not None and timeout_until > now:
                timeout_members.append(
                    (member, timeout_until)
                )

        if not timeout_members:
            await interaction.followup.send(
                embed=create_embed(
                    "🔇 Timeout Members",
                    "現在タイムアウトされているメンバーはいません。"
                )
            )
            return

        timeout_members.sort(
            key=lambda x: x[0].display_name.lower()
        )

        lines = []

        for member, timeout_until in timeout_members:
            timestamp = int(timeout_until.timestamp())

            lines.append(
                f"• {member.mention} ・解除 <t:{timestamp}:R>"
            )

        await send_member_list(
            interaction,
            lines,
            "🔇 Timeout Members"
        )

    except Exception:
        print("Error in /timeoutmemberslist:")
        traceback.print_exc()

        if interaction.response.is_done():
            await interaction.followup.send(
                embed=create_embed(
                    "❌ Error",
                    "コマンドの実行中にエラーが発生しました。"
                )
            )
        else:
            await interaction.response.send_message(
                embed=create_embed(
                    "❌ Error",
                    "コマンドの実行中にエラーが発生しました。"
                )
            )


@timeoutmemberslist.error
async def timeoutmemberslist_error(
    interaction: discord.Interaction,
    error
):
    print("Slash command permission/error:")

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
        message = "❌ コマンドの実行中にエラーが発生しました。"

    if interaction.response.is_done():
        await interaction.followup.send(message)
    else:
        await interaction.response.send_message(message)


class RoleListView(discord.ui.View):
    def __init__(self, interaction, roles, members):
        super().__init__(timeout=180)

        self.author_id = interaction.user.id
        self.roles = roles
        self.members = members

        self.page = 0
        self.per_page = 20

        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ このボタンはコマンドを実行した本人のみ使用できます。",
                ephemeral=True
            )
            return False

        return True

    def max_page(self):
        if not self.roles:
            return 1

        return (
            len(self.roles) + self.per_page - 1
        ) // self.per_page

    def current_roles(self):
        start = self.page * self.per_page
        end = start + self.per_page

        return self.roles[start:end]

    def page_text(self):
        current_roles = self.current_roles()

        if not current_roles:
            return "ロールがありません。"

        lines = [
            "📋 **Role List**",
            "",
            "確認したいロールのボタンを押してください。",
            ""
        ]

        for role in current_roles:
            lines.append(
                f"**{role.name}**"
            )

        lines.append("")
        lines.append(
            f"ページ {self.page + 1} / {self.max_page()}"
        )

        return "\n".join(lines)

    def update_buttons(self):
        self.clear_items()

        current_roles = self.current_roles()

        for role in current_roles:
            button = discord.ui.Button(
                label=role.name[:80],
                style=discord.ButtonStyle.secondary
            )

            async def callback(
                interaction: discord.Interaction,
                selected_role=role
            ):
                role_members = [
                    member
                    for member in self.members
                    if selected_role in member.roles
                ]

                role_members.sort(
                    key=lambda member:
                    member.display_name.lower()
                )

                lines = [
                    member.mention
                    for member in role_members
                ]

                if not lines:
                    await interaction.response.send_message(
                        embed=create_embed(
                            f"👥 {selected_role.name}",
                            "このロールを持っているメンバーはいません。"
                        ),
                        ephemeral=True
                    )
                    return

                chunks = split_message(lines)

                if len(chunks) == 1:
                    await interaction.response.send_message(
                        content=f"👥 {selected_role.name}\n{chunks[0]}"
                    )
                    return

                view = OutputConfirmView(
                    interaction,
                    chunks,
                    f"👥 {selected_role.name}"
                )

                await interaction.response.send_message(
                    embed=create_embed(
                        "📋 出力確認",
                        f"このロールのメンバー一覧は "
                        f"**{len(chunks)}個** に分かれます。\n"
                        "全員分を出力しますか？"
                    ),
                    view=view
                )

            button.callback = callback
            self.add_item(button)

        previous_button = discord.ui.Button(
            label="◀ 前へ",
            style=discord.ButtonStyle.primary,
            disabled=(self.page <= 0)
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
        self.add_item(previous_button)

        next_button = discord.ui.Button(
            label="次へ ▶",
            style=discord.ButtonStyle.primary,
            disabled=(
                self.page >= self.max_page() - 1
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
        self.add_item(next_button)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


@bot.tree.command(
    name="rolelistup",
    description="サーバーのロール一覧を表示します"
)
async def rolelistup(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "このコマンドはサーバー内でのみ使用できます。"
            )
            return

        members = await fetch_all_members(guild)

        roles = [
            role
            for role in guild.roles
            if not role.is_default()
        ]

        roles.sort(
            key=lambda role: role.position,
            reverse=True
        )

        view = RoleListView(
            interaction,
            roles,
            members
        )

        await interaction.followup.send(
            content=view.page_text(),
            view=view
        )

    except Exception:
        print("Error in /rolelistup:")
        traceback.print_exc()

        if interaction.response.is_done():
            await interaction.followup.send(
                embed=create_embed(
                    "❌ Error",
                    "コマンドの実行中にエラーが発生しました。"
                )
            )
        else:
            await interaction.response.send_message(
                embed=create_embed(
                    "❌ Error",
                    "コマンドの実行中にエラーが発生しました。"
                )
            )


@bot.tree.command(
    name="allmemberlistup",
    description="サーバー全員のメンバーをロール別に表示します"
)
async def allmemberlistup(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "このコマンドはサーバー内でのみ使用できます。"
            )
            return

        members = await fetch_all_members(guild)

        roles = [
            role
            for role in guild.roles
            if not role.is_default()
        ]

        roles.sort(
            key=lambda role: role.position,
            reverse=True
        )

        lines = [
            "📋 **All Member List 👇**"
        ]

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
                key=lambda member:
                member.display_name.lower()
            )

            lines.append("")
            lines.append(
                f"**@ {role.name}**"
            )

            for member in role_members:
                lines.append(
                    member.mention
                )
                assigned_member_ids.add(member.id)

        no_role_members = [
            member
            for member in members
            if member.id not in assigned_member_ids
        ]

        no_role_members.sort(
            key=lambda member:
            member.display_name.lower()
        )

        if no_role_members:
            lines.append("")
            lines.append(
                "**【ロールなし】**"
            )

            for member in no_role_members:
                lines.append(
                    member.mention
                )

        await send_member_list(
            interaction,
            lines,
            "📋 All Member List 👇"
        )

    except Exception:
        print("Error in /allmemberlistup:")
        traceback.print_exc()

        if interaction.response.is_done():
            await interaction.followup.send(
                embed=create_embed(
                    "❌ Error",
                    "コマンドの実行中にエラーが発生しました。"
                )
            )
        else:
            await interaction.response.send_message(
                embed=create_embed(
                    "❌ Error",
                    "コマンドの実行中にエラーが発生しました。"
                )
            )


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


async def main():
    await start_web_server()
    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

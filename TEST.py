import discord
import os
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

TRIGGER_CHANNEL_ID = 1384136861580001383
CATEGORY_ID = 910158683026128919

user_channels = {}
channel_passwords = {}

# ===== 控制面板 =====
class ControlPanel(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    def is_owner(self, interaction):
        return interaction.user.id == self.user_id

    @discord.ui.button(label="👢 踢人", style=discord.ButtonStyle.danger)
    async def kick(self, interaction, button):
        if not self.is_owner(interaction):
            await interaction.response.send_message("這不是你的控制面板", ephemeral=True)
            return

        channel = bot.get_channel(user_channels.get(self.user_id))
        if not channel or len(channel.members) <= 1:
            await interaction.response.send_message("沒有可踢的成員", ephemeral=True)
            return

        await interaction.response.send_message(
            "選擇要踢的人：",
            view=KickView(channel, self.user_id),
            ephemeral=True
        )

    @discord.ui.button(label="🔒 上鎖", style=discord.ButtonStyle.danger)
    async def lock(self, interaction, button):
        if not self.is_owner(interaction):
            await interaction.response.send_message("這不是你的控制面板", ephemeral=True)
            return
        await interaction.response.send_modal(LockModal())

    @discord.ui.button(label="🔓 解鎖", style=discord.ButtonStyle.success)
    async def unlock(self, interaction, button):
        if not self.is_owner(interaction):
            await interaction.response.send_message("這不是你的控制面板", ephemeral=True)
            return

        channel = bot.get_channel(user_channels.get(self.user_id))
        guild = channel.guild

        await channel.set_permissions(guild.default_role, connect=True)

        for target, perms in channel.overwrites.items():
            if isinstance(target, discord.Member) and perms.connect is False:
                await channel.set_permissions(target, overwrite=None)

        channel_passwords.pop(channel.id, None)

        await interaction.response.send_message("已解鎖（已洗白）", ephemeral=True)

    @discord.ui.button(label="👥 人數限制", style=discord.ButtonStyle.primary)
    async def limit(self, interaction, button):
        if not self.is_owner(interaction):
            await interaction.response.send_message("這不是你的控制面板", ephemeral=True)
            return
        await interaction.response.send_modal(LimitModal())

    @discord.ui.button(label="✏️ 改名", style=discord.ButtonStyle.secondary)
    async def rename(self, interaction, button):
        if not self.is_owner(interaction):
            await interaction.response.send_message("這不是你的控制面板", ephemeral=True)
            return
        await interaction.response.send_modal(RenameModal())


# ===== Modal =====
class LockModal(discord.ui.Modal, title="設定密碼"):
    password = discord.ui.TextInput(label="密碼")

    async def on_submit(self, interaction):
        channel = bot.get_channel(user_channels.get(interaction.user.id))
        channel_passwords[channel.id] = self.password.value

        await channel.set_permissions(channel.guild.default_role, connect=False)
        await channel.set_permissions(interaction.user, connect=True)

        await interaction.response.send_message("已上鎖", ephemeral=True)


class RenameModal(discord.ui.Modal, title="改名"):
    name = discord.ui.TextInput(label="名稱")

    async def on_submit(self, interaction):
        channel = bot.get_channel(user_channels.get(interaction.user.id))
        await channel.edit(name=self.name.value)
        await interaction.response.send_message("已改名", ephemeral=True)


class LimitModal(discord.ui.Modal, title="人數限制"):
    limit = discord.ui.TextInput(label="0~99")

    async def on_submit(self, interaction):
        try:
            value = int(self.limit.value)
        except:
            await interaction.response.send_message("請輸入數字", ephemeral=True)
            return

        channel = bot.get_channel(user_channels.get(interaction.user.id))
        await channel.edit(user_limit=value)
        await interaction.response.send_message("已設定", ephemeral=True)


# ===== 踢人 =====
class MemberSelect(discord.ui.Select):
    def __init__(self, channel, user_id):
        self.channel = channel
        self.user_id = user_id

        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in channel.members
        ]

        super().__init__(options=options[:25])

    async def callback(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("這不是你的控制面板", ephemeral=True)
            return

        member = self.channel.guild.get_member(int(self.values[0]))
        await member.move_to(None)

        if self.channel.id in channel_passwords:
            await self.channel.set_permissions(member, connect=False)

        try:
            await member.send("你已被踢出，請重新輸入密碼加入")
        except:
            pass

        await interaction.response.send_message("已踢出", ephemeral=True)


class KickView(discord.ui.View):
    def __init__(self, channel, user_id):
        super().__init__(timeout=60)
        self.add_item(MemberSelect(channel, user_id))


# ===== 語音事件 =====
@bot.event
async def on_voice_state_update(member, before, after):

    # 建立頻道
    if after.channel and after.channel.id == TRIGGER_CHANNEL_ID:
        guild = member.guild
        category = guild.get_channel(CATEGORY_ID)

        new_channel = await guild.create_voice_channel(
            name=f"{member.display_name} 的房間",
            category=category
        )

        await member.move_to(new_channel)
        user_channels[member.id] = new_channel.id

        try:
            await new_channel.send(
                embed=discord.Embed(title="控制面板"),
                view=ControlPanel(member.id)
            )
        except:
            pass

    # 刪除頻道
    if before.channel:
        channel = before.channel
        if channel.id in user_channels.values():
            if len(channel.members) == 0:
                try:
                    await channel.delete()
                except:
                    pass

                for uid, cid in list(user_channels.items()):
                    if cid == channel.id:
                        del user_channels[uid]

                channel_passwords.pop(channel.id, None)

# ====== /改名 ======
@bot.tree.command(name="改名", description="修改你的語音頻道名稱")
@app_commands.describe(名稱="新的頻道名稱")
async def rename_channel(interaction: discord.Interaction, 名稱: str):

    user_id = interaction.user.id
    channel_id = user_channels.get(user_id)

    if not channel_id:
        await interaction.response.send_message("你沒有語音頻道", ephemeral=True)
        return

    channel = bot.get_channel(channel_id)

    if not channel:
        await interaction.response.send_message("找不到頻道", ephemeral=True)
        return

    await channel.edit(name=名稱)
    await interaction.response.send_message(f"已改名為：{名稱}", ephemeral=True)


# ====== /上鎖 ======
@bot.tree.command(name="上鎖", description="鎖定語音頻道")
@app_commands.describe(密碼="設定的密碼")
async def lock_channel(interaction: discord.Interaction, 密碼: str):

    user_id = interaction.user.id
    channel_id = user_channels.get(user_id)

    if not channel_id:
        await interaction.response.send_message("你沒有頻道", ephemeral=True)
        return

    channel = bot.get_channel(channel_id)

    channel_passwords[channel.id] = 密碼

    await channel.set_permissions(channel.guild.default_role, connect=False)
    await channel.set_permissions(interaction.user, connect=True)

    await interaction.response.send_message("已上鎖", ephemeral=True)


# ====== /解鎖 ======
@bot.tree.command(name="解鎖", description="解除語音頻道鎖定")
async def unlock_channel(interaction: discord.Interaction):

    user_id = interaction.user.id
    channel_id = user_channels.get(user_id)

    if not channel_id:
        await interaction.response.send_message("你沒有頻道", ephemeral=True)
        return

    channel = bot.get_channel(channel_id)

    # 🔒 房主驗證（重要）
    owner_id = None
    for uid, ch_id in user_channels.items():
        if ch_id == channel.id:
            owner_id = uid
            break

    if owner_id != interaction.user.id:
        await interaction.response.send_message("這不是你的頻道", ephemeral=True)
        return

    await channel.set_permissions(channel.guild.default_role, connect=True)

    for target, perms in channel.overwrites.items():
        if isinstance(target, discord.Member) and perms.connect is False:
            await channel.set_permissions(target, overwrite=None)

    channel_passwords.pop(channel.id, None)

    await interaction.response.send_message("已解鎖（已洗白）", ephemeral=True)


# ====== /人數限制 ======
@bot.tree.command(name="人數限制", description="設定語音頻道人數上限")
@app_commands.describe(人數="0~99（0=不限）")
async def set_limit(interaction: discord.Interaction, 人數: int):

    user_id = interaction.user.id
    channel_id = user_channels.get(user_id)

    if not channel_id:
        await interaction.response.send_message("你沒有頻道", ephemeral=True)
        return

    if 人數 < 0 or 人數 > 99:
        await interaction.response.send_message("範圍需 0~99", ephemeral=True)
        return

    channel = bot.get_channel(channel_id)
    await channel.edit(user_limit=人數)

    await interaction.response.send_message(f"已設定：{人數}", ephemeral=True)


# ====== /加入頻道 ======
@bot.tree.command(name="加入頻道", description="輸入密碼加入語音頻道")
@app_commands.describe(密碼="頻道密碼")
async def join_channel(interaction: discord.Interaction, 密碼: str):

    user = interaction.user

    for channel_id, pwd in channel_passwords.items():
        if pwd == 密碼:

            channel = bot.get_channel(channel_id)

            await channel.set_permissions(user, connect=True)

            await interaction.response.send_message(
                f"已取得權限，請加入：{channel.name}",
                ephemeral=True
            )
            return

    await interaction.response.send_message("密碼錯誤", ephemeral=True)


# ====== /踢出 ======
@bot.tree.command(name="踢出", description="踢出指定成員")
@app_commands.describe(member="要踢的人")
async def kick_member(interaction: discord.Interaction, member: discord.Member):

    user_id = interaction.user.id
    channel_id = user_channels.get(user_id)

    if not channel_id:
        await interaction.response.send_message("你沒有頻道", ephemeral=True)
        return

    channel = bot.get_channel(channel_id)

    if member.voice is None or member.voice.channel != channel:
        await interaction.response.send_message("該成員不在你的頻道", ephemeral=True)
        return

    if member.id == interaction.user.id:
        await interaction.response.send_message("不能踢自己", ephemeral=True)
        return

    await member.move_to(None)

    locked = channel.id in channel_passwords
    if locked:
        await channel.set_permissions(member, connect=False)

    try:
        await member.send(
            "🔒 請重新輸入 /加入頻道 密碼"
            if locked else "⚠️ 您已被中斷連線"
        )
    except:
        pass

    await interaction.response.send_message("已踢出", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot Ready")


bot.run(os.getenv("TOKEN"))

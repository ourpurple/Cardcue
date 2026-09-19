"""Run inside the API container: python -m cardcue_api.admin.cli create-admin."""
import argparse
import asyncio
import getpass
from sqlalchemy import select, delete
from cardcue_api.admin.models import AdminUser, WebSession
from cardcue_api.admin.security import password_hash
from cardcue_api.config import settings
from cardcue_api.persistence.database import async_session_factory

async def run(action, username, password):
    settings.validate_production()
    async with async_session_factory() as session:
        user = (await session.execute(select(AdminUser).where(AdminUser.username == username))).scalar_one_or_none()
        if action == "create-admin":
            if (await session.execute(select(AdminUser.id).limit(1))).first():
                raise SystemExit("管理员已存在；使用 reset-password 恢复访问")
            session.add(AdminUser(username=username, password_hash=password_hash(password)))
        else:
            if not user:
                raise SystemExit("管理员不存在")
            user.password_hash = password_hash(password)
            await session.execute(delete(WebSession).where(WebSession.admin_id == user.id))
        await session.commit()
    print("管理员已更新；没有输出或保存明文密码。")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create-admin", "reset-password"])
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    password = getpass.getpass("管理员密码（至少 14 个字符）: ")
    if len(password) < 14 or len(password) > 256 or password != getpass.getpass("再次输入: "):
        raise SystemExit("密码长度不合要求或两次输入不一致")
    asyncio.run(run(args.action, args.username, password))

if __name__ == "__main__":
    main()

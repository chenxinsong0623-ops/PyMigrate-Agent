"""参数 annotation 为 BaseModel receiver 提供静态证明。"""

from pydantic import BaseModel as ModelBase


class Account(ModelBase):
    account_id: int
    owner: str


def export_account(account: Account) -> str:
    return account.schema_json()


class PlainAccount:
    def schema_json(self) -> str:
        return "{}"


plain = PlainAccount()
plain.schema_json()


def unknown_export(account):
    return account.schema_json()


FORMAT = "json-schema"
VERSION = "v1"


def export_metadata() -> tuple[str, str]:
    return FORMAT, VERSION

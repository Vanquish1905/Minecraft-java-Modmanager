"""Player accounts: offline accounts and Microsoft accounts (device-code login)."""
from __future__ import annotations

import hashlib
import time
import uuid as uuidlib
from dataclasses import asdict, dataclass, fields
from typing import Callable, Optional

from . import net
from .config import Paths, read_json, write_json_atomic

MS_DEVICE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
SCOPE = "XboxLive.signin offline_access"


def offline_uuid(name: str) -> str:
    """Same UUID the vanilla server gives offline players (Java's nameUUIDFromBytes)."""
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuidlib.UUID(bytes=bytes(digest)))


def valid_offline_name(name: str) -> bool:
    return 3 <= len(name) <= 16 and all(c.isalnum() or c == "_" for c in name) and name.isascii()


@dataclass
class Account:
    kind: str                 # "offline" | "msa"
    name: str
    uuid: str
    access_token: str = "0"
    refresh_token: str = ""
    expires_at: float = 0.0
    xuid: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({'Microsoft' if self.kind == 'msa' else 'Offline'})"

    @classmethod
    def from_dict(cls, d: dict) -> "Account":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


class AccountStore:
    def __init__(self, paths: Paths):
        self.paths = paths
        data = read_json(paths.accounts_file, {}) or {}
        self.accounts: list[Account] = [Account.from_dict(a) for a in data.get("accounts", [])]
        self.default_uuid: str = data.get("default", "")

    def save(self) -> None:
        write_json_atomic(self.paths.accounts_file, {
            "accounts": [asdict(a) for a in self.accounts],
            "default": self.default_uuid,
        }, private=True)

    def default(self) -> Optional[Account]:
        for a in self.accounts:
            if a.uuid == self.default_uuid:
                return a
        return self.accounts[0] if self.accounts else None

    def set_default(self, acc: Account) -> None:
        self.default_uuid = acc.uuid
        self.save()

    def add(self, acc: Account) -> None:
        self.accounts = [a for a in self.accounts if a.uuid != acc.uuid]
        self.accounts.append(acc)
        if not self.default_uuid or len(self.accounts) == 1:
            self.default_uuid = acc.uuid
        self.save()

    def remove(self, acc: Account) -> None:
        self.accounts = [a for a in self.accounts if a.uuid != acc.uuid]
        if self.default_uuid == acc.uuid:
            self.default_uuid = self.accounts[0].uuid if self.accounts else ""
        self.save()

    def add_offline(self, name: str) -> Account:
        if not valid_offline_name(name):
            raise ValueError("Names must be 3-16 characters: letters, numbers and _ only.")
        acc = Account("offline", name, offline_uuid(name))
        self.add(acc)
        return acc


# --------------------------------------------------------------------------- Microsoft

class AuthError(Exception):
    pass


XSTS_ERRORS = {
    2148916233: "This Microsoft account has no Xbox profile. Sign in once at minecraft.net and try again.",
    2148916235: "Xbox Live is not available in your country.",
    2148916236: "This account needs adult verification (South Korea).",
    2148916237: "This account needs adult verification (South Korea).",
    2148916238: "This is a child account; it must be added to a Family by an adult.",
}


def start_device_login(client_id: str) -> dict:
    """Returns {'user_code', 'verification_uri', 'device_code', 'interval', 'expires_in', 'message'}."""
    if not client_id:
        raise AuthError("Microsoft login needs an Azure application (client) ID. Set it in Settings.")
    return net.post_form(MS_DEVICE_URL, {"client_id": client_id, "scope": SCOPE})


def poll_device_login(client_id: str, device: dict, cancelled: Callable[[], bool]) -> dict:
    interval = int(device.get("interval", 5))
    deadline = time.time() + int(device.get("expires_in", 900))
    while time.time() < deadline:
        if cancelled():
            raise AuthError("Login cancelled")
        time.sleep(interval)
        try:
            return net.post_form(MS_TOKEN_URL, {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id, "device_code": device["device_code"]})
        except net.HTTPStatusError as e:
            err = (e.json() or {}).get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 5
                continue
            raise AuthError(f"Microsoft login failed: {err or e}")
    raise AuthError("Login code expired")


def _minecraft_from_ms_token(ms_token: dict) -> Account:
    try:
        xbl = net.post_json(XBL_URL, {
            "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com",
                           "RpsTicket": "d=" + ms_token["access_token"]},
            "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"})
        uhs = xbl["DisplayClaims"]["xui"][0]["uhs"]
        try:
            xsts = net.post_json(XSTS_URL, {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl["Token"]]},
                "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"})
        except net.HTTPStatusError as e:
            code = (e.json() or {}).get("XErr")
            raise AuthError(XSTS_ERRORS.get(code, f"Xbox authorisation failed ({code or e.code})"))
        mc = net.post_json(MC_LOGIN_URL, {"identityToken": f"XBL3.0 x={uhs};{xsts['Token']}"})
        token = mc["access_token"]
        try:
            profile = net.get_json(MC_PROFILE_URL, headers={"Authorization": f"Bearer {token}"})
        except net.HTTPStatusError as e:
            if e.code == 404:
                raise AuthError("This Microsoft account does not own Minecraft: Java Edition.")
            raise
        raw = profile["id"]
        return Account("msa", profile["name"], str(uuidlib.UUID(raw)), token,
                       ms_token.get("refresh_token", ""), time.time() + int(mc.get("expires_in", 86400)),
                       xuid=(xsts.get("DisplayClaims", {}).get("xui", [{}])[0].get("xid", "")))
    except net.HTTPStatusError as e:
        if e.code == 403 and "minecraftservices" in e.url:
            raise AuthError("Minecraft services rejected this Azure app. New app IDs must be approved "
                            "by Mojang before they can log in.")
        raise AuthError(str(e))


def complete_login(ms_token: dict) -> Account:
    return _minecraft_from_ms_token(ms_token)


def refresh(acc: Account, client_id: str) -> Account:
    """Refresh a Microsoft account's Minecraft token if it is about to expire."""
    if acc.kind != "msa" or time.time() < acc.expires_at - 300:
        return acc
    if not acc.refresh_token or not client_id:
        raise AuthError("Your Microsoft login expired. Please remove and add the account again.")
    try:
        ms = net.post_form(MS_TOKEN_URL, {"grant_type": "refresh_token", "client_id": client_id,
                                          "refresh_token": acc.refresh_token, "scope": SCOPE})
    except net.HTTPStatusError:
        raise AuthError("Your Microsoft login expired. Please remove and add the account again.")
    new = _minecraft_from_ms_token(ms)
    if not new.refresh_token:
        new.refresh_token = acc.refresh_token
    return new

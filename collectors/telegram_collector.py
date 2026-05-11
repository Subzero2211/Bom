"""
collectors/telegram_collector.py

Telegram public kanallarını izler.
Telethon kütüphanesi kullanır — bot değil, kullanıcı hesabı ile çalışır.
İlk çalıştırmada telefon numarası + SMS kodu ister, sonra session kaydeder.

Kurulum:
    pip install telethon

Konfigürasyon (config.py):
    TELEGRAM["api_id"]   = my.telegram.org'dan al (ücretsiz)
    TELEGRAM["api_hash"] = aynı sayfadan
    TELEGRAM["phone"]    = "+905xxxxxxxxx"
    TELEGRAM["channels"] = ["bbcnewsturkce", "Reuters", ...]
"""

import hashlib
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from models.event import RawEvent, Domain, GeoPoint
from collectors.base import BaseCollector
from config import TELEGRAM

log = logging.getLogger("Collector.Telegram")


class TelegramCollector(BaseCollector):
    name = "telegram"
    domain = Domain.SOCIAL

    def __init__(self):
        super().__init__()
        self._client = None
        self._session_file = "telegram_session"

    def collect(self) -> list[RawEvent]:
        """Senkron wrapper — asyncio event loop'u çalıştırır."""
        if not TELEGRAM.get("api_id") or not TELEGRAM.get("api_hash"):
            self.log.info("Telegram API key yok — atlanıyor")
            return []

        try:
            # Mevcut event loop varsa kullan, yoksa yeni oluştur
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return loop.run_until_complete(self._async_collect())
        except Exception as e:
            self.log.error("Telegram toplama hatası: %s", e)
            return []

    async def _async_collect(self) -> list[RawEvent]:
        from telethon import TelegramClient
        from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

        events = []
        since = datetime.utcnow() - timedelta(hours=2)

        try:
            async with TelegramClient(
                self._session_file,
                int(TELEGRAM["api_id"]),
                TELEGRAM["api_hash"],
            ) as client:
                # İlk çalıştırmada otomatik giriş ister
                if not await client.is_user_authorized():
                    await client.send_code_request(TELEGRAM["phone"])
                    code = input("Telegram doğrulama kodu: ")
                    await client.sign_in(TELEGRAM["phone"], code)

                for channel in TELEGRAM.get("channels", []):
                    try:
                        ch_events = await self._read_channel(client, channel, since)
                        events.extend(ch_events)
                        self.log.debug("@%s: %d mesaj", channel, len(ch_events))
                    except Exception as e:
                        self.log.warning("@%s okuma hatası: %s", channel, e)

        except Exception as e:
            self.log.error("Telegram bağlantı hatası: %s", e)

        return events

    async def _read_channel(self, client, channel: str, since: datetime) -> list[RawEvent]:
        events = []
        try:
            entity = await client.get_entity(channel)
            async for msg in client.iter_messages(entity, limit=30):
                # Zaman filtresi
                msg_time = msg.date.replace(tzinfo=None)
                if msg_time < since:
                    break

                if not msg.text or len(msg.text.strip()) < 20:
                    continue

                ev = self._parse_message(msg, channel, msg_time)
                if ev:
                    events.append(ev)

        except Exception as e:
            self.log.debug("Kanal %s hata: %s", channel, e)

        return events

    def _parse_message(self, msg, channel: str, ts: datetime) -> Optional[RawEvent]:
        try:
            text = msg.text.strip()
            if not text:
                return None

            # İlk satır başlık, geri kalan body
            lines = text.split("\n", 1)
            title = lines[0][:200]
            body = lines[1].strip()[:500] if len(lines) > 1 else None

            keywords = self.match_keywords(text)
            entities = self.extract_entities(text)

            # Keyword yoksa düşük değer — ama yine de kaydet (sosyal sinyal)
            event_id = hashlib.md5(f"{channel}_{msg.id}".encode()).hexdigest()[:16]

            # Mesaj linki
            url = f"https://t.me/{channel}/{msg.id}"

            # Görüntülenme sayısı (varsa)
            views = getattr(msg, "views", 0) or 0

            return RawEvent(
                source=f"telegram_{channel}",
                domain=Domain.SOCIAL,
                event_id=f"tg_{event_id}",
                title=title,
                body=body,
                url=url,
                timestamp=ts,
                keywords_matched=keywords,
                entities=entities,
                raw_data={
                    "channel": channel,
                    "message_id": msg.id,
                    "views": views,
                    "forwards": getattr(msg, "forwards", 0) or 0,
                    "replies": getattr(msg.replies, "replies", 0) if msg.replies else 0,
                    "has_media": msg.media is not None,
                },
            )
        except Exception as e:
            self.log.debug("Mesaj parse hatası: %s", e)
            return None

"""
collectors/reddit_collector.py

Reddit — r/worldnews, r/geopolitics, r/CredibleDefense vb.
PRAW kütüphanesi: pip install praw
Ücretsiz uygulama: https://www.reddit.com/prefs/apps → "script" tipi
"""

import praw
from datetime import datetime
from models.event import RawEvent, Domain
from collectors.base import BaseCollector
from config import REDDIT, REDDIT_SUBS


class RedditCollector(BaseCollector):
    name = "reddit"
    domain = Domain.SOCIAL

    def collect(self) -> list[RawEvent]:
        if not REDDIT["client_id"] or not REDDIT["client_secret"]:
            self.log.info("Reddit API key yok — atlanıyor")
            return []

        try:
            reddit = praw.Reddit(
                client_id=REDDIT["client_id"],
                client_secret=REDDIT["client_secret"],
                user_agent=REDDIT["user_agent"],
            )
            # Bağlantıyı test et
            reddit.user.me()
        except Exception as e:
            # Read-only mode da çalışır (kullanıcı girişi gerekmez)
            try:
                reddit = praw.Reddit(
                    client_id=REDDIT["client_id"],
                    client_secret=REDDIT["client_secret"],
                    user_agent=REDDIT["user_agent"],
                )
            except Exception as e2:
                self.log.error("Reddit bağlantı hatası: %s", e2)
                return []

        events = []
        for sub_name in REDDIT_SUBS:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.hot(limit=20):
                    ev = self._parse_post(post, sub_name)
                    if ev:
                        events.append(ev)
            except Exception as e:
                self.log.warning("r/%s hata: %s", sub_name, e)

        self.log.info("%d Reddit postu toplandı", len(events))
        return events

    def _parse_post(self, post, sub_name: str) -> RawEvent | None:
        try:
            title = post.title
            selftext = post.selftext[:400] if post.selftext else ""
            full_text = f"{title} {selftext}"

            keywords = self.match_keywords(full_text)
            # Düşük kaliteli veya ilgisiz postları filtrele
            if not keywords and post.score < 100:
                return None

            entities = self.extract_entities(full_text)
            ts = datetime.utcfromtimestamp(post.created_utc)

            return RawEvent(
                source=f"reddit_{sub_name}",
                domain=Domain.SOCIAL,
                event_id=f"reddit_{post.id}",
                title=title,
                body=selftext if selftext else None,
                url=f"https://reddit.com{post.permalink}",
                timestamp=ts,
                keywords_matched=keywords,
                entities=entities,
                raw_data={
                    "score": post.score,
                    "upvote_ratio": post.upvote_ratio,
                    "num_comments": post.num_comments,
                    "subreddit": sub_name,
                    "flair": post.link_flair_text or "",
                    "is_self": post.is_self,
                },
            )
        except Exception as e:
            self.log.debug("Reddit post parse hatası: %s", e)
            return None

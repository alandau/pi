# coding: utf-8
from __future__ import unicode_literals

import re
import itertools

from .common import InfoExtractor
from ..compat import (
    compat_str,
)
from ..utils import (
    determine_ext,
    unified_strdate,
)


class OnlineLifeIE(InfoExtractor):
    IE_NAME = 'online-life'
    IE_DESC = 'Online-Life videos'
    _VALID_URL = r'https?://www\.online-life\.(?:[\w]+)/(?P<id>[\d]+)-.*\.html'

    _TESTS = [{
        'url': 'http://www.online-life.in/16879-zlo-vnutri-the-evil-within-2017.html',
        'info_dict' : {
            'id': '16879',
            'title': 'Зло внутри (The Evil Within) 2017',
            'ext': 'mp4',
        }
    }, {
        'url': 'http://www.online-life.in/16051-pyatero-vernulis-domoy-five-came-back-2017.html',
        'info_dict': {
        },
        'playlist_mincount': 3,
    }]

    @staticmethod
    def _extract_urls(webpage):
        return [iframes.group('url') for iframes in re.finditer(
            r'<iframe[^>]+?src=(["\'])(?P<url>(?:https?:)?//dterod\.com/player.php\?newsid=[\d]+.*?)\1',
            webpage)]

    def _real_extract(self, url):
        video_id = self._match_id(url)
        html_url = 'http://dterod.com/player.php?newsid=%s' % video_id
        dterod_data = self._download_webpage('http://dterod.com/js.php?id=%s' % video_id, video_id=video_id,
                headers={'Referer': html_url}, encoding='cp1251')
        js = self._search_regex(r'[^}]*({[^}]*?})', dterod_data, video_id)
        match = re.search(r'["\']?pl["\']?\s*:\s*"(?P<playlist>[^"]*?)"', js)
        if match:
            playlist_url = match.group('playlist')
            top = self._download_json(playlist_url, video_id)
            entries = []
            for  p1 in top['playlist']:
                if 'playlist' in p1:
                    for p2 in p1['playlist']:
                        entries.append(dict(id=p2['file'], title=p2['comment'], url=p2['file']))
                elif 'file' in p1:
                    entries.append(dict(id=p1['file'], title=p1['comment'], url=p1['file']))
            return self.playlist_result(entries)

        url = self._search_regex(r'["\']?file["\']?\s*:\s*"([^"]*?)"', js, video_id)
        title = self._search_regex(r'["\']?comment["\']?\s*:\s*"([^"]*?)"', js, video_id, default=url)
        return {
            'id': video_id,
            'title': title,
            'url': url,
        }

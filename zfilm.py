# coding: utf-8
from __future__ import unicode_literals

import re
import json

from .common import InfoExtractor
from ..utils import (
    RegexNotFoundError,
    ExtractorError,
)

class ZfilmIE(InfoExtractor):
    IE_NAME = 'zfilm-online'
    IE_DESC = 'Zfilm-Online videos'
    # https://e.zfilm-online.xyz/
    # https://w.online-life-hd.xyz/
    _VALID_URL = r'(?P<id>https?://[a-z0-9-]*\.(?:zfilm-online|online-life-hd)\.xyz/.*)'

    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:62.0) Gecko/20100101 Firefox/62.0'

    def _real_extract(self, url):
        headers = {'User-Agent': self.UA, 'Referer': url}
        video_id = self._match_id(url)

        main_page = self._download_webpage(url, video_id, headers=headers)
        iframe_url = self._search_regex(r'<iframe .*?src="([^"]+assistir-filme\.biz/video(?:\?[^"]*)?)"', main_page, video_id)
        iframe_page = self._download_webpage(iframe_url, video_id, headers=headers)
        final_page_url = self._search_regex(r'<script.*?"src":"(https://[a-z0-9-]*\.assistir-filme\.biz[^"]*)".*?</script', iframe_page, video_id)
        headers['Referer'] = iframe_url
        final_page = self._download_webpage(final_page_url, video_id, headers=headers)
        file_text = self._search_regex(r'file:([^\n]*)', final_page, video_id)

        if file_text.endswith('\n'):
            file_text = file_text[:-1]
        if file_text.endswith(','):
            file_text = file_text[:-1]
        file_text = file_text[1:-1] # remove quotes

        if not file_text.startswith('['):
            hls_url = file_text
            # regular url
            return {
                'id': video_id,
                'title': video_id,
                'formats': self._extract_m3u8_formats(hls_url, url),
            }

        # playlist
        entries = []
        j = json.loads(file_text)
        for translation_dict in j:
            for season_dict in translation_dict['folder']:
                for episode_dict in season_dict['folder']:
                    title = '{} - {} - {}'.format(translation_dict['title'], season_dict['title'], episode_dict['title'])
                    videourl = episode_dict['file']
                    entries.append(dict(id=videourl, title=title, url=videourl))

        return self.playlist_result(entries)

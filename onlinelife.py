# coding: utf-8
from __future__ import unicode_literals

import re
import itertools
import binascii
import base64
import json
from Crypto.Cipher import AES

from .common import InfoExtractor
from ..compat import (
    compat_str,
    compat_urllib_parse_urlencode,
)
from ..utils import (
    determine_ext,
    unified_strdate,
    int_or_none,
    RegexNotFoundError,
)


class OnlineLifeIE(InfoExtractor):
    IE_NAME = 'online-life'
    IE_DESC = 'Online-Life videos'
    _VALID_URL = r'https?://www\.online-?life\.(?:[\w]+)/(?P<id>[\d]+)-.*\.html'

    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:62.0) Gecko/20100101 Firefox/62.0'
    KEY = 'c0236b8bdc4cb8922bcaa51b1281a5abefd1d56efd8bce51225a953589954b5d'
    IV = 'debea2f78027e090ff750a2e22d2b806'

    def _real_extract(self, url):
        headers = {'User-Agent': self.UA, 'Referer': url}

        video_id = self._match_id(url)
        main_page = self._download_webpage(url, video_id, headers=headers)
        try:
            moonwalk_url = self._search_regex(r'<iframe .*?src="([^"]+/iframe)"', main_page, video_id)
        except RegexNotFoundError as e:
            return self._real_extract_old_format(url)
        mastarti_page = self._download_webpage(moonwalk_url, video_id, headers=headers)
        partner_id = self._search_regex(r'partner_id: ([0-9]+)', mastarti_page, video_id)
        domain_id = self._search_regex(r'domain_id: ([0-9]+)', mastarti_page, video_id)
        host = self._search_regex(r'''host: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        proto = self._search_regex(r'''proto: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        video_token = self._search_regex(r'''video_token: ['"]([^'"]+)['"]''', mastarti_page, video_id)

        dic = {
            'a': partner_id,
            'b': domain_id,
            'c': False,
            'e': video_token,
            'f': self.UA,
        }

        plaintext = json.dumps(dic)
        pad_value = 16 - len(plaintext) % 16
        padding = chr(pad_value) * pad_value
        ciphertext = AES.new(binascii.unhexlify(self.KEY), AES.MODE_CBC, binascii.unhexlify(self.IV)).encrypt(plaintext + padding)
        cipher_base64 = base64.b64encode(ciphertext)
        mp4_or_m3u = self._download_json(proto + host + '/vs', video_id, headers=headers, data=compat_urllib_parse_urlencode({'q': cipher_base64}))
        if u'mp4' in mp4_or_m3u:
            quality_json_url = mp4_or_m3u[u'mp4']
            quality_json = self._download_json(quality_json_url, video_id, headers=headers)
            formats = []
            for (q, url) in quality_json.items():
                formats.append({
                    'url': url,
                    'manifest_url': url,
                    'format_id': q,
                    'height': int_or_none(q),
                })
        elif u'm3u8' in mp4_or_m3u:
            quality_selector_url = mp4_or_m3u[u'm3u8']
            quality_selector_m3u = self._download_webpage(quality_selector_url, video_id, headers=headers)
            formats = self._parse_m3u8_formats(quality_selector_m3u, video_id)
        else:
            raise Exception("Can't parse /vs output")

        self._sort_formats(formats)

        return {
            'id': video_id,
            'title': 'ttt',
            'formats': formats,
        }

    def _real_extract_old_format(self, url):
        video_id = self._match_id(url)
        html_url = 'http://cidwo.com/player.php?newsid=%s' % video_id
        dterod_data = self._download_webpage('http://cidwo.com/js.php?id=%s' % video_id, video_id=video_id,
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

# coding: utf-8
from __future__ import unicode_literals

import re
import itertools
import binascii
import base64
import json
import urllib
from Crypto.Cipher import AES
import time

from .common import InfoExtractor
from ..compat import (
    compat_str,
    compat_urllib_parse_urlencode,
    compat_parse_qs,
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
    _VALID_URL = r'https?://www\.online-?life\.(?:[\w]+)/(?P<id>[\d]+)-.*\.html|^onlinelife://onlinelife\?.*'

    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:62.0) Gecko/20100101 Firefox/62.0'

    def _real_extract(self, url):
        headers = {'User-Agent': self.UA, 'Referer': url}

        if url.startswith('onlinelife://onlinelife?'):
            return self.get_one_episode(url, headers)

        video_id = self._match_id(url)
        main_page = self._download_webpage(url, video_id, headers=headers)
        try:
            moonwalk_url = self._search_regex(r'<iframe .*?src="([^"]+/iframe)"', main_page, video_id)
        except RegexNotFoundError as e:
            return self._real_extract_old_format(url)

        if self._downloader.params.get('noplaylist'):
            # Get just video if both playlist and video available
            return self.handle_one_video(moonwalk_url, video_id, headers)

        mastarti_page = self._download_webpage(moonwalk_url, video_id, headers=headers)
        seasons = self._search_regex(r'seasons: \[([\d,\s]+)\]', mastarti_page, video_id, fatal=False)
        if not seasons:
            # No playlist available, get just video
            return self.handle_one_video(moonwalk_url, video_id, headers)

        # Get playlist
        entries = []
        host = self._search_regex(r'''host: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        proto = self._search_regex(r'''proto: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        url_prefix = proto + host
        ref = self._search_regex(r'''ref: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        serial_id = self._search_regex(r'''serial_token: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        translations = self._search_regex(r'translations: \[(\[.*\])\]', mastarti_page, video_id, fatal=False)
        if translations:
            t = re.findall(r'"([^"]*)"', translations)
            # (serial_id, translation_name)
            translations = zip(t[::2], t[1::2])
            if not translations:
                translations = [(serial_id, "Unknown")]
        else:
            translations = [(serial_id, "Unknown")]

        for (serial_id, trans_name) in translations:
            translations_url = url_prefix + '/serial/{serial}/iframe?season=1&episode=1&ref={ref}'.format(serial=serial_id, ref=ref)
            translations_page = self._download_webpage(translations_url, video_id, headers=headers)
            seasons = self._search_regex(r'seasons: \[([\d,\s]+)\]', translations_page, video_id, fatal=False)
            if not seasons:
                continue
            seasons = [s.strip() for s in seasons.split(',')]
            for season in seasons:
                season_url = url_prefix + '/serial/{serial}/iframe?season={season}&episode=1&ref={ref}'.format(serial=serial_id, season=season, ref=ref)
                season_page = self._download_webpage(season_url, video_id, headers=headers)
                episodes = self._search_regex(r'episodes: \[([\d,\s]*)\]', season_page, video_id)
                episodes = [e.strip() for e in episodes.split(',')]
                for episode in episodes:
                    title = 'Translation {} Season {} Episode {}'.format(trans_name, season, episode)
                    videourl = 'onlinelife://onlinelife?origurl={origurl}&serial={serial}&season={season}&episode={episode}'.format(origurl=urllib.quote(url), serial=serial_id, season=season, episode=episode)
                    entries.append(dict(id=videourl, title=title, url=videourl))

        return self.playlist_result(entries)

    def get_one_episode(self, url, headers):
        qs = url[url.index('?')+1:]
        params = compat_parse_qs(qs)
        origurl = params['origurl'][0]
        serial_id = params['serial'][0]
        season = params['season'][0]
        episode = params['episode'][0]

        video_id = url
        main_page = self._download_webpage(origurl, video_id, headers=headers)
        moonwalk_url = self._search_regex(r'<iframe .*?src="([^"]+/iframe)"', main_page, video_id)
        mastarti_page = self._download_webpage(moonwalk_url, video_id, headers=headers)
        ref = self._search_regex(r'''ref: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        host = self._search_regex(r'''host: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        proto = self._search_regex(r'''proto: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        url_prefix = proto + host
        episode_url = url_prefix + '/serial/{serial}/iframe?season={season}&episode={episode}&ref={ref}'.format(serial=serial_id, season=season, episode=episode, ref=ref)
        return self.handle_one_video(episode_url, video_id, headers)

    def handle_one_video(self, url, video_id, headers):
        """
        url looks like:
        http://moonwalk.cc/serial/0c0ebb8924c4183e5d387de8f0ba8b17/iframe
        http://mastarti.com/serial/d08f6dc93c19f80c0b22b18048c15cab/iframe?season=16&episode=4&ref=...
        """
        mastarti_page = self._download_webpage(url, video_id, headers=headers)
        ref = self._search_regex(r'''ref: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        partner_id = self._search_regex(r'partner_id: ([0-9]+)', mastarti_page, video_id)
        domain_id = self._search_regex(r'domain_id: ([0-9]+)', mastarti_page, video_id)
        host = self._search_regex(r'''host: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        proto = self._search_regex(r'''proto: ['"]([^'"]+)['"]''', mastarti_page, video_id)
        video_token = self._search_regex(r'''video_token: ['"]([^'"]+)['"]''', mastarti_page, video_id)

        url_prefix = proto + host

        (key, iv) = self.get_key_and_iv(mastarti_page, url_prefix, video_id, headers)

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
        ciphertext = AES.new(binascii.unhexlify(key), AES.MODE_CBC, binascii.unhexlify(iv)).encrypt(plaintext + padding)
        cipher_base64 = base64.b64encode(ciphertext)
        mp4_or_m3u = self._download_json(url_prefix + '/vs', video_id, headers=headers, data=compat_urllib_parse_urlencode({'q': cipher_base64, 'ref': ref}))
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
            'title': video_id,
            'formats': formats,
        }

    def get_key_and_iv(self, mastarti_page, url_prefix, video_id, headers):
        js_url = self._search_regex(r'<script src="(/assets/video-[^.]*\.js)">', mastarti_page, video_id)
        js_url = url_prefix + js_url
        js = self._download_webpage(js_url, video_id, headers=headers)
        js = js[js.index('getVideoManifests:') : js.index('onGetManifestSuccess:')]
        js = js.replace('\n', '')
        m = re.search(r'\(([a-z]),(\d+)\)', js)
        if not m:
            raise Exception("Can't get rotate amount")
        r_var = m.group(1)
        rotate_amt = int(m.group(2))

        m = re.search(r'([a-z])\[([a-z])\("0x[0-9a-f]{1,2}"\)\]', js)
        if not m:
            raise Exception("Can't get e array and o function var names")
        e_name = m.group(1)
        o_name = m.group(2)

        r_str = self._search_regex(r_var + r'=\[(.*?)\];', js, video_id)
        e_str = self._search_regex(r';(' + e_name + r'[[.][^;]*);', js, video_id)

        m = re.search(r'\(([a-z])\).{,10}iv:.*?\(([a-z])\)', js)
        if not m:
            raise Exception("Can't get key and iv vars")
        key_var = m.group(1)
        iv_var = m.group(2)
        s = self._search_regex(r'\b' + key_var + r'=([^,;]*)[,;]', js, video_id) # key
        a = self._search_regex(r'\b' + iv_var + r'=([^,;]*)[,;]', js, video_id) # iv

        r_str = r_str[1:-1]
        r = [elem for elem in r_str.split('","')]
        rotate_amt = rotate_amt % len(r)
        for i in range(rotate_amt):
            r = r[1:] + r[0:1]

        e = {}
        def evaluate(s):
            terms = s.split('+')
            if len(terms) > 1:
                return ''.join(evaluate(t) for t in terms)
            # No + in expression
            if s.startswith(e_name + '.'):
                return e[s[2:]]
            if s.startswith(e_name + '['):
                if not s.endswith(']'):
                    raise Exception("Can't evaluate {}".format(s))
                return e[evaluate(s[2:-1])]
            if s.startswith('"'):
                if not s.endswith('"'):
                    raise Exception("Can't evaluate {}".format(s))
                return s[1:-1]
            m = re.match(r'(\d+)', s)
            if m:
                return m.group(1)
            m = re.match(o_name + r'\("((?:0x)?[0-9a-fA-F]+)"\)$', s)
            if m:
                return r[int(m.group(1), base=0)]
            raise Exception("Can't evaluate {}, unknown format".format(s))

        for elem in e_str.split(','):
            # elem look like e[x]=z or e.y=z
            # x is a string or o("0x1d")
            # y is a js identifier
            # z is o("0x11") or "80" or e[one_of_the_above] or sum_of_above
            if '=' not in elem:
                continue
            (left, right) = elem.split('=')
            if left[0] != e_name:
                raise Exception('Bad format of e assignment')
            if left[1] == '.':
                attr = left[2:]
            elif left[1] == '[':
                if left[-1] != ']':
                    raise Exception('Bad format of e[ assigment')
                attr = left[2:-1]
                attr = evaluate(attr)
            else:
                raise Exception('Bad char after e in assigment')
            val = evaluate(right)
            e[attr] = val

        return (evaluate(s), evaluate(a))

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

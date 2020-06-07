#!/usr/bin/env python

import sys
import Tkinter as tk
import tkMessageBox
import tkFileDialog
import tkFont
import dbus
import os.path
import time
import subprocess
import json
import glob
import traceback

PLAYLIST_DIR = os.path.expanduser('~/playlists')

def getuser():
    import pwd
    return pwd.getpwuid(os.getuid())[0]

def secToStr(sec):
    if sec < 3600:
        return '%d:%02d' % (sec // 60, sec % 60)
    else:
        return '%d:%02d:%02d' % (sec // 3600, (sec // 60) % 60, sec % 60)

def sanitifyFilename(name):
    return name.replace('/', '-').replace('\n',' ')

class PlayerWindow(tk.Toplevel):
    def __init__(self, master, url, close_callback, start_time):
        tk.Toplevel.__init__(self, master)
        self.close_callback = close_callback
        self.geometry('500x500')
        self.attributes("-fullscreen", True)
        self.after_idle(lambda: (self.lift(), self.attributes("-topmost", True)))
        dbus_filename = '/tmp/omxplayerdbus.' + getuser()
        args = ['/usr/bin/omxplayer', '--aspect-mode', 'letterbox', '--avdict', 'reconnect:1,reconnect_at_eof:1']
        if start_time:
            args.extend(['--pos', start_time])
        args.append(url)
        self.omx = subprocess.Popen(args)
        retries = 20
        while True:
            try:
                with open(dbus_filename) as dbusname:
                    path = dbusname.readline().rstrip()
                    if not path:
                        raise IOError()
                    bus = dbus.bus.BusConnection(path)
                    break
            except (IOError, dbus.DBusException):
                time.sleep(0.05)
                retries -= 1
                if retries == 0:
                    self.close()
                    return
        retries = 20
        while True:
            try:
                remote_object = bus.get_object("org.mpris.MediaPlayer2.omxplayer", "/org/mpris/MediaPlayer2", introspect=False)
                break
            except dbus.DBusException:
                time.sleep(0.05)
                retries -= 1
                if retries == 0:
                    self.close()
                    return
        self.dbusif_player = dbus.Interface(remote_object, 'org.mpris.MediaPlayer2.Player')
        self.dbusif_props = dbus.Interface(remote_object, 'org.freedesktop.DBus.Properties')

        self.leftIsDown = False
        self.hasScrolled = False
        self.volumedB = 0
        self.timer = None
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.screenWidth = self.winfo_screenwidth()
        self.screenHeight = self.winfo_screenheight()

        frame = tk.Frame(self, background='black')
        frame.pack(fill=tk.BOTH, expand=1)
        frame.bind('<Button-1>', self.left_down)
        frame.bind('<ButtonRelease-1>', self.left_up)
        frame.bind('<Button-3>', lambda e: self.showHideControls())
        frame.bind('<Button-4>', lambda e: self.scroll(-1)) # scroll up
        frame.bind('<Button-5>', lambda e: self.scroll(1)) # scroll down
        self.bind('<Key>', self.keypress)

        self.frame = frame = tk.Frame(self)
        tk.Button(frame, text='Stop', command=lambda: self.close(True)).pack(side=tk.LEFT)
        tk.Button(frame, text='Minimize', command=self.iconify).pack(side=tk.LEFT)
        tk.Button(frame, text='Play/Pause', command=self.playpause).pack(side=tk.LEFT)
        self.posLabel = tk.Label(frame, text='0:00')
        self.posLabel.pack(side=tk.LEFT)
        self.curPosVar = tk.IntVar()
        self.scale = tk.Scale(frame, variable=self.curPosVar, showvalue=False, orient=tk.HORIZONTAL, bigincrement=5)
        self.scale.pack(side=tk.LEFT, fill=tk.X, expand=1)
        self.scale.bind('<Button-1>', lambda e: self.stopTimer())
        self.scale.bind('<ButtonRelease-1>', lambda e: self.scaleChangedUsingMouse())
        self.curPosVar.trace('w', lambda *args: self.posLabel.config(text=secToStr(self.curPosVar.get())))
        self.controlsShown = False
        self.paused = False

        retries = 5
        while True:
            try:
                self.duration = long(self.dbusif_props.Duration()) // 1000000
                break
            except dbus.DBusException:
                time.sleep(0.05)
                retries -= 1
                if retries == 0:
                    self.close()
                    return
        tk.Label(frame, text=secToStr(self.duration)).pack(side=tk.LEFT)
        self.scale.config(to_=self.duration)

        self.bind('<Unmap>', lambda e: self.showHideVideo(False) if e.widget == self else None)
        self.bind('<Map>', lambda e: self.showHideVideo(True) if e.widget == self else None)
        self.timerTimeout()

    def scaleChangedUsingMouse(self):
        print(long(self.scale.get()) * 1000000)
        try:
            self.dbusif_player.SetPosition(dbus.ObjectPath('/not/used'), long(self.scale.get()) * 1000000)
        except dbus.DBusException as e:
            traceback.print_exc()
            self.close()
        self.timerTimeout()
    def left_down(self, event):
        if self.omx.poll() is not None:
            self.close()
            return
        self.leftDownX = event.x
        self.leftDownY = event.y
        self.leftIsDown = True
    def left_up(self, event):
        if not self.leftIsDown:
            return
        self.leftIsDown = False
        #if self.leftDownX - 10 <= event.x <= self.leftDownX + 10 and \
        #   self.leftDownY - 10 <= event.y <= self.leftDownY + 10 and \
        #   not self.hasScrolled:
        if not self.hasScrolled:
               self.playpause()
        self.hasScrolled = False
    def scroll(self, amount):
        if not self.leftIsDown:
            return
        self.hasScrolled = True
        try:
            amount_sec = long(amount) * 5
            if amount_sec < 0:
                # If rewinding, rewind an extra 3 seconds to account for
                # the player looking for the _next_ I-frame
                amount_sec -= 3
            self.dbusif_player.Seek(amount_sec * 1000000) # Seek relative in us
        except dbus.DBusException as e:
            traceback.print_exc()
            self.close()
    def close(self, manual=False):
        if hasattr(self, 'dbusif_player'):
            try:
                self.dbusif_player.Action(15) # Exit
            except dbus.DBusException as e:
                traceback.print_exc()
        time.sleep(0.5)
        try:
            self.omx.terminate()
        except OSError:
            pass
        subprocess.call('killall omxplayer.bin 2>/dev/null', shell=True)
        self.omx.wait()
        self.destroy()
        if self.close_callback:
            self.close_callback(manual)
    def playpause(self):
        print("Play/pause")
        self.paused = not self.paused
        if self.paused:
            self.pauseTime = time.time()
        else:
            pass
#            if time.time() - self.pauseTime > 20:   # in seconds
#                try:
#                    self.dbusif_player.Seek(long(-1)) # Seek relative in us
#                except dbus.DBusException as e:
#                    traceback.print_exc()
        try:
            self.dbusif_player.Action(16) # PlayPause
        except dbus.DBusException as e:
            traceback.print_exc()
            self.close()
    def showHideControls(self):
        if self.omx.poll() is not None:
            self.close()
            return
        self.controlsShown = not self.controlsShown
        if self.controlsShown:
            self.frame.pack(fill=tk.X)
            geom = '0 0 %d %d' % (self.screenWidth, self.screenHeight - 70)
        else:
            self.frame.pack_forget()
            geom = '0 0 0 0'
        try:
            self.dbusif_player.VideoPos(dbus.ObjectPath('/not/used'), geom)
        except dbus.DBusException as e:
            traceback.print_exc()
            self.close()
    def stopTimer(self):
        if self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None
    def timerTimeout(self):
        if self.omx.poll() is not None:
            self.close()
            return
        try:
            self.scale.set(self.dbusif_props.Position() // 1000000)
        except dbus.DBusException as e:
            traceback.print_exc()
            self.close()
            return
        self.timer = self.after(1000, self.timerTimeout)
    def showHideVideo(self, show):
        try:
            if show:
                self.dbusif_player.Action(29) # Unhide Video
            else:
                self.dbusif_player.Action(28) # Hide Video
        except dbus.DBusException as e:
            traceback.print_exc()
            self.close()
    def keypress(self, event):
        if event.char == ' ':
            pass


class MainWindow(tk.Tk):
    def __init__(self, url, action, start_time):
        tk.Tk.__init__(self)
        for fontname in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            tkFont.nametofont(fontname).configure(size=-14)
        self.geometry('1200x400')
        frame = tk.Frame(self)
        frame.pack(fill=tk.X)
        tk.Label(frame, text='URL: ').pack(side=tk.LEFT)
        self.text = tk.Entry(frame, width=50)
        self.text.pack(side=tk.LEFT, fill=tk.X, expand=1)
        def paste():
            clear()
            try:
                self.text.insert(0, self.clipboard_get().strip())
            except tk.TclError:
                # CLIPBOARD selection doesn't exist or form "STRING" not defined
                pass
        def clear():
            self.text.delete(0, tk.END)
        def copy():
            self.clipboard_clear()
            self.clipboard_append(self.text.get())
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='Clear & Paste', command=paste)
        menu.add_command(label='Clear', command=clear)
        menu.add_command(label='Copy', command=copy)
        self.text.bind('<Button-3>', lambda e: menu.post(e.x_root, e.y_root))
        if url is not None:
            self.text.insert(0, url)
        else:
            paste()

        frame = tk.Frame(self)
        frame.pack()
        bb=tk.Button(frame, text='Play', command=lambda: (self.autoplay.set(0), self.cmd_play())).pack(side=tk.LEFT)
        tk.Button(frame, text='Get Youtube playlist', command=self.cmd_get_youtube_playlist).pack(side=tk.LEFT)
        tk.Button(frame, text='Add to playlist', command=self.cmd_add_to_playlist).pack(side=tk.LEFT)

        # -----
        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=1)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=3)
        self.playlists = tk.Listbox(frame)
        self.playlists.grid(row=0, column=0, sticky=tk.N+tk.S+tk.W+tk.E)
        self.playlists.bind('<ButtonRelease-1>', lambda e: self.load_playlist())
        self.playlist = tk.Listbox(frame)
        self.playlist.grid(row=0, column=1, sticky=tk.N+tk.S+tk.W+tk.E)

        fr = tk.Frame(frame)
        fr.grid(row=1, column=0)
        tk.Button(fr, text='qqq').pack(side=tk.LEFT)

        fr = tk.Frame(frame)
        fr.grid(row=1, column=1)
        tk.Button(fr, text="Play", command=self.cmd_playlist_play).pack(side=tk.LEFT)
        tk.Button(fr, text='Get Youtube playlist', command=self.cmd_playlist_get_youtube_playlist).pack(side=tk.LEFT)
        tk.Button(fr, text="Save playlist", command=self.cmd_playlist_save).pack(side=tk.LEFT)
        self.autoplay = tk.IntVar()
        tk.Checkbutton(fr, text='Autoplay', variable=self.autoplay).pack(side=tk.LEFT)

        self.load_playlists()
        self.playlistData = []
        self.playlistTitle = 'playlist'

        if action == 'play':
            self.after_idle(lambda: self.cmd_play(start_time))
        elif action == 'get-youtube-playlist':
            self.cmd_get_youtube_playlist()
    def play(self, url, start_time=None):
        if not (url.endswith('.mp4') or url.endswith('.m3u8')):
            try:
                args = ['youtube-dl', '-f', 'best[height<=?720]', '-g', '--no-playlist', '--', url]
                url = subprocess.check_output(args, stderr=subprocess.STDOUT).strip()
            except subprocess.CalledProcessError as e:
                tkMessageBox.showerror('Youtube', "Can't get video url: %s" % e.output)
                return
            print("Got direct video url: %s" % url)
            sys.stdout.flush()
        player = PlayerWindow(self, url, self.player_closed, start_time)
    def cmd_play(self, start_time=None):
        self.play(self.text.get(), start_time)
    def cmd_playlist_play(self):
        sel = self.playlist.curselection()
        if not sel:
            return
        self.play(self.playlistData[sel[0]]['url'])
    def get_youtube_playlist(self, url):
        try:
            args = ['youtube-dl', '--flat-playlist', '--yes-playlist', '-J', '--', url]
            jsonstr = subprocess.check_output(args, stderr=subprocess.STDOUT).strip()
        except subprocess.CalledProcessError as e:
            tkMessageBox.showerror('Youtube', "Can't get playlist: %s" % e.output)
            return
        try:
            j = json.loads(jsonstr)
        except ValueError as e:
            tkMessageBox('Youtube', "Can't decode json playlist: %s" % e)
            return
        self.playlist.delete(0, tk.END)
        self.playlistData = []
        self.playlistTitle = sanitifyFilename(j.get('title', ''))
        try:
            for e in j['entries']:
                title = e.get('title', e['url'])
                self.playlistData.append(dict(url=e['url'], title=title))
                self.playlist.insert(tk.END, title)
        except KeyError as e:
            tkMessageBox('Youtube', "Can't decode playlist: %s" % e)
            return
    def cmd_get_youtube_playlist(self):
        self.get_youtube_playlist(self.text.get().strip())
    def cmd_playlist_get_youtube_playlist(self):
        sel = self.playlist.curselection()
        if not sel:
            return
        self.get_youtube_playlist(self.playlistData[sel[0]]['url'])
    def cmd_add_to_playlist(self):
        url = self.text.get().strip()
        self.playlistData.append(dict(url=url, title=url))
        self.playlist.insert(tk.END, url)

    def cmd_playlist_save(self):
        name = tkFileDialog.asksaveasfilename(parent=self, filetypes=[('M3U Playlists', '.m3u*'), ('All Files', '*')],
                defaultextension='.m3u', initialdir=PLAYLIST_DIR, initialfile=self.playlistTitle,
                confirmoverwrite=True)
        if not name:
            return
        if not name.endswith('.m3u'):
            name += '.m3u'
        with open(name, mode='w') as f:
            f.write('#EXTM3U\n')
            for line in self.playlistData:
                if line['title'] != line['url']:
                    f.write('#EXTINF:0,%s\n' % line['title'].encode('utf-8'))
                f.write('%s\n' % line['url'])
        self.load_playlists()
    def load_playlists(self):
        self.playlists.delete(0, tk.END)
        for l in sorted(glob.glob(os.path.join(PLAYLIST_DIR, '*.m3u')), key=lambda s: s.lower()):
            name = os.path.basename(l)[:-4]
            self.playlists.insert(tk.END, name)
    def load_playlist(self):
        sel = self.playlists.curselection()
        if not sel:
            return
        basename = self.playlists.get(sel[0])
        filename = os.path.join(PLAYLIST_DIR, basename + '.m3u')
        self.playlistTitle = basename
        with open(filename) as f:
            lines = f.readlines()
        self.playlistData = []
        self.playlist.delete(0, tk.END)
        if not lines:
            return
        if lines[0].strip() != '#EXTM3U':
            for l in lines:
                url = l.strip()
                self.playlistData.append(dict(url=url, title=url))
                self.playlist.insert(tk.END, url)
            return
        i = 1
        title = None
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if line.startswith('#EXTINF:'):
                split = line[8:].split(',', 1)
                title = split[0] if len(split) == 1 else split[1]
                continue
            url = line
            if not title:
                title = url
            self.playlistData.append(dict(url=url, title=title))
            self.playlist.insert(tk.END, title)
            title = None

    def player_closed(self, manual):
        if manual or not self.autoplay.get():
            self.autoplay.set(0)
            return
        # Advance to next playlist item
        sel = self.playlist.curselection()
        if not sel:
            return
        sel = sel[0] + 1
        if sel >= self.playlist.size():
            self.autoplay.set(0)
            return
        self.playlist.see(sel)
        self.playlist.activate(sel)
        self.playlist.selection_clear(0, tk.END)
        self.playlist.selection_set(sel)
        self.cmd_playlist_play()


def time_str_to_sec(s):
    if ':' not in s:
        return s
    a = s.split(':')
    # If mm:ss, prepend hh:
    if len(a) == 2:
        a.insert(0, '0')
    return ':'.join(a)

def main():
    url = None
    action = None
    start_time = None
    if len(sys.argv) >= 2:
        url = sys.argv[1]
        if len(sys.argv) >= 3:
            action = sys.argv[2]
            if len(sys.argv) >= 4:
                start_time = time_str_to_sec(sys.argv[3])
    root = MainWindow(url, action, start_time)
    root.mainloop()

if __name__ == '__main__':
	main()

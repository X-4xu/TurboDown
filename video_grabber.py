import yt_dlp
import os
import subprocess
import shutil

def get_ffmpeg_dir():
    """
    Ensure we have a directory containing 'ffmpeg.exe' named correctly,
    so that yt-dlp can find and use it for merging.
    """
    project_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(project_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    
    ffmpeg_exe_path = os.path.join(bin_dir, "ffmpeg.exe")
    
    # If it already exists, return the directory
    if os.path.exists(ffmpeg_exe_path):
        return bin_dir

    # Otherwise, copy from imageio_ffmpeg
    try:
        import imageio_ffmpeg
        src_path = imageio_ffmpeg.get_ffmpeg_exe()
        if src_path and os.path.exists(src_path):
            import shutil
            shutil.copy2(src_path, ffmpeg_exe_path)
            print(f"[FFmpeg] Successfully set up local ffmpeg at: {ffmpeg_exe_path}")
            return bin_dir
    except Exception as e:
        print(f"[FFmpeg] Error setting up local ffmpeg: {e}")

    # Fallback to system PATH
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return os.path.dirname(sys_ffmpeg)

    return None

def is_ffmpeg_available():
    return get_ffmpeg_dir() is not None

def get_video_info(url):
    """
    Extracts video info using yt-dlp.
    Returns a dict with title, thumbnail, duration, and list of downloadable formats.
    """
    ydl_opts = {
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # If it's a playlist, get the first video or return error
            if 'entries' in info:
                # We handle the first video of the playlist
                entries = list(info['entries'])
                if not entries:
                    raise Exception("Empty playlist")
                info = entries[0]
                
            title = info.get('title', 'Video')
            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)
            formats = info.get('formats', [])
            
            parsed_formats = []
            seen_resolutions = set()
            
            # We want to extract:
            # 1. Pre-merged (video + audio) formats (typically up to 720p)
            # 2. High quality video-only formats (like 1080p, 1440p, 4K)
            # 3. Audio-only formats (MP3/M4A)
            
            ffmpeg_exists = is_ffmpeg_available()
            
            for f in formats:
                f_id = f.get('format_id')
                ext = f.get('ext', 'mp4')
                filesize = f.get('filesize') or f.get('filesize_approx') or 0
                
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')
                
                is_video = vcodec != 'none'
                is_audio = acodec != 'none'
                
                # Format resolution label
                res_height = f.get('height')
                if is_video and res_height:
                    res_label = f"{res_height}p"
                elif is_audio and not is_video:
                    res_label = "Audio Only"
                else:
                    continue
                
                # Check format types
                if is_video and is_audio:
                    # Pre-merged
                    label = f"Video + Audio ({res_label})"
                    type_str = "merged"
                elif is_video and not is_audio:
                    # Video only (requires ffmpeg to merge with audio)
                    suffix = "" if ffmpeg_exists else " (No Audio - needs FFMPEG)"
                    label = f"Video Only ({res_label}){suffix}"
                    type_str = "video_only"
                elif is_audio and not is_video:
                    # Audio only
                    abr = f.get('abr')
                    abr_label = f" ({int(abr)}kbps)" if abr else ""
                    label = f"Audio Only {ext.upper()}{abr_label}"
                    type_str = "audio_only"
                else:
                    continue
                
                # Avoid duplicate resolutions for video_only if they are same resolution
                res_key = (type_str, res_label, ext)
                if res_key in seen_resolutions:
                    continue
                seen_resolutions.add(res_key)
                
                # File size text
                size_str = "Unknown"
                if filesize > 0:
                    if filesize < 1024*1024:
                        size_str = f"{filesize/1024:.1f} KB"
                    else:
                        size_str = f"{filesize/(1024*1024):.1f} MB"
                
                parsed_formats.append({
                    "format_id": f_id,
                    "label": label,
                    "resolution": res_label,
                    "ext": ext,
                    "size_str": size_str,
                    "filesize": filesize,
                    "type": type_str,
                    "url": f.get('url') # Direct stream URL
                })
                
            # Sort formats by resolution height or size
            def sort_key(x):
                # Put merged first, then video_only, then audio
                type_priority = {"merged": 0, "video_only": 1, "audio_only": 2}
                # Resolution priority
                height = 0
                if x["resolution"].replace("p", "").isdigit():
                    height = int(x["resolution"].replace("p", ""))
                return (type_priority.get(x["type"], 3), -height, -x["filesize"])
                
            parsed_formats.sort(key=sort_key)
            
            return {
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration,
                "formats": parsed_formats,
                "webpage_url": info.get('webpage_url', url)
            }
    except Exception as e:
        print(f"yt-dlp extract error: {e}")
        return None

def download_video_format(url, format_id, dest_path, progress_callback=None, stop_event=None):
    """
    Downloads a video with a specific format using yt-dlp directly.
    We use this since yt-dlp handles combining audio/video (using ffmpeg) and complex streams.
    """
    class YtDlpLogger:
        def debug(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): print(msg)

    # yt-dlp progress hook
    def my_hook(d):
        if stop_event and stop_event.is_set():
            raise Exception("Download Cancelled")
            
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0) or 0
            eta = d.get('eta', 0) or 0
            
            if progress_callback:
                progress_callback(downloaded, total, speed, eta)
        elif d['status'] == 'finished':
            if progress_callback:
                progress_callback(d.get('downloaded_bytes', 0), d.get('downloaded_bytes', 0), 0, 0)

    # Configure options
    # If format_id is video_only and ffmpeg is available, download best audio too and merge
    ffmpeg_exists = is_ffmpeg_available()
    
    # We find if format_id is video-only
    # If it is, and ffmpeg exists, we ask yt-dlp to merge bestvideo/bestaudio
    if format_id and "+" not in format_id and ffmpeg_exists:
        # Check if the format is video-only by querying yt-dlp first or just using format_id+bestaudio
        # Actually, yt-dlp supports: format_id+bestaudio
        format_spec = f"{format_id}+bestaudio/best"
    else:
        format_spec = format_id if format_id else 'best'

    ffmpeg_dir = get_ffmpeg_dir()

    ydl_opts = {
        'format': format_spec,
        'outtmpl': dest_path,
        'nocheckcertificate': True,
        'logger': YtDlpLogger(),
        'progress_hooks': [my_hook],
        'quiet': True,
        'no_warnings': True,
    }
    if ffmpeg_dir:
        ydl_opts['ffmpeg_location'] = ffmpeg_dir
        if "+" in format_spec:
            ydl_opts['merge_output_format'] = 'mp4'
    
    # yt-dlp will auto-append extension unless outtmpl forces it,
    # so we should strip extension if yt-dlp handles it, or use absolute outtmpl
    # We remove extension from outtmpl and let yt-dlp handle extension
    base, ext = os.path.splitext(dest_path)
    # We configure outtmpl to be the base and we let yt-dlp decide extension
    ydl_opts['outtmpl'] = base + '.%(ext)s'
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        
    # Get actual output file
    # yt-dlp might have saved it as base.mp4 or base.mkv or base.webm
    # Let's search for base.*
    parent = os.path.dirname(dest_path)
    basename = os.path.basename(base)
    for f in os.listdir(parent):
        if f.startswith(basename) and f != basename + ".meta":
            return os.path.join(parent, f)
            
    return dest_path

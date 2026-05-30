import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

# Suppress Flask logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Global queues for communication with GUI
download_queue = None
youtube_queue = None
_app_ref = None  # Reference to the main app for status

@app.route('/add', methods=['POST'])
def add_download():
    if not request.json:
        return jsonify({"success": False, "error": "Invalid request"}), 400
        
    url = request.json.get('url')
    filename = request.json.get('filename', '')
    referer = request.json.get('referer', '')
    
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400
        
    print(f"[Server] Received download request from browser: {url}")
    
    if download_queue:
        download_queue.put({
            "url": url,
            "filename": filename,
            "referer": referer
        })
        return jsonify({"success": True, "message": "Link sent to Download Manager"}), 200
    else:
        return jsonify({"success": False, "error": "Download Manager is not running"}), 503

@app.route('/youtube', methods=['POST'])
def youtube_download():
    if not request.json:
        return jsonify({"success": False, "error": "Invalid request"}), 400
    
    url = request.json.get('url')
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400
    
    print(f"[Server] Received YouTube request from browser: {url}")
    
    if youtube_queue:
        youtube_queue.put({"url": url})
        return jsonify({"success": True, "message": "YouTube link sent to Download Manager"}), 200
    else:
        return jsonify({"success": False, "error": "Download Manager is not running"}), 503

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({"status": "running", "app": "TurboDown - Download Manager"}), 200

@app.route('/downloads', methods=['GET'])
def get_downloads():
    """Return list of active downloads for extension popup."""
    if _app_ref and hasattr(_app_ref, 'downloads'):
        active = []
        for dl_id, dl in list(_app_ref.downloads.items())[:10]:
            active.append({
                "id": dl_id,
                "filename": dl.get("filename", ""),
                "status": dl.get("status", ""),
                "progress": int((dl.get("downloaded", 0) / max(dl.get("size", 1), 1)) * 100),
                "speed": dl.get("speed", "0 KB/s")
            })
        return jsonify({"success": True, "downloads": active}), 200
    return jsonify({"success": True, "downloads": []}), 200

@app.route('/intercept', methods=['POST'])
def toggle_intercept():
    """Toggle download interception from extension."""
    data = request.json or {}
    enabled = data.get('enabled', True)
    return jsonify({"success": True, "intercept": enabled}), 200

def start_server(queue_instance, yt_queue=None, app_ref=None, port=9000):
    global download_queue, youtube_queue, _app_ref
    download_queue = queue_instance
    youtube_queue = yt_queue
    _app_ref = app_ref
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)

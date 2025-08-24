import sounddevice as sd
import numpy as np
import wave
import base64
import requests
import pygame
import time
import os
import webrtcvad
import threading
import keyboard
from aip import AipSpeech
from config import BAIDU_API_KEY, BAIDU_SECRET_KEY, BAIDU_ASR_URL
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext

ASR_CONFIG = {
    "api_key": BAIDU_API_KEY,
    "secret_key": BAIDU_SECRET_KEY,
    "url": BAIDU_ASR_URL,
    "dev_pid": 1537
}

TTS_CONFIG = {
    "app_id": "119812145",
    "api_key": "p9vdGZYrapwbhRNLVtBos2yi",
    "secret_key": "CQxpf1UWJlZEwKbUCfpgKryfbhtGU4hl",
    "default_out": "response.mp3",
    "per": 0,
    "vol": 5,
    "spd": 5,
    "pit": 5,
    "daily_char_limit": 999000
}

tts_client = AipSpeech(TTS_CONFIG["app_id"], TTS_CONFIG["api_key"], TTS_CONFIG["secret_key"])

CHAR_COUNT_FILE = "tts_char_count.txt"
VAD_CONFIG = {
    "mode": 2,
    "sample_rate": 16000,
    "frame_duration_ms": 30,
    "silence_threshold": 100,
    "loud_sound_frames": 5,
    "min_loud_frames": 1,
    "max_loud_frames": 30
}
VAD_FRAME_SIZE = int(VAD_CONFIG["sample_rate"] * VAD_CONFIG["frame_duration_ms"] / 1000)

conversation_history = []
waiting_for_wakeup = True
DEFAULT_MIC = None
input_mode = "voice"
mode_lock = threading.Lock()
ai_background = ""
show_control_panel = False
wake_word = "你好"

def setup_mode_switch_listener():
    def on_enter_press():
        global input_mode
        with mode_lock:
            if input_mode != "text":
                input_mode = "text"
                print("\n⌨️ 已切换到文字输入模式（按Tab键返回语音输入）")

    def on_tab_press():
        global input_mode
        with mode_lock:
            if input_mode != "voice":
                input_mode = "voice"
                print("\n🎤 已切换到语音输入模式（按Enter键切换到文字输入）")

    def on_alt_press():
        global show_control_panel
        if not waiting_for_wakeup:
            show_control_panel = True
            print("\n⌨️ 检测到Alt键，已设置show_control_panel=True")

    keyboard.add_hotkey('enter', on_enter_press)
    keyboard.add_hotkey('tab', on_tab_press)
    keyboard.add_hotkey('alt', on_alt_press)
    print("⌨️ 快捷键：按Enter切换文字输入，Tab切换语音输入，Alt打开控制面板")

def get_text_input(prompt: str = "请输入文字: ") -> str:
    root = tk.Tk()
    root.withdraw()
    user_input = simpledialog.askstring("文字输入", prompt)
    root.destroy()
    return user_input.strip() if user_input else ""

def create_control_panel():
    global ai_background, conversation_history, waiting_for_wakeup, wake_word

    root = tk.Tk()
    root.title("语音助手参数控制面板")
    root.geometry("600x600")
    root.resizable(False, False)

    main_frame = tk.Frame(root)
    main_frame.pack(fill=tk.BOTH, expand=1)
    canvas = tk.Canvas(main_frame)
    scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    current_params = {
        "vad_mode": VAD_CONFIG["mode"],
        "vad_silence": VAD_CONFIG["silence_threshold"],
        "vad_loud": VAD_CONFIG["loud_sound_frames"],
        "tts_vol": TTS_CONFIG["vol"],
        "tts_spd": TTS_CONFIG["spd"],
        "tts_pit": TTS_CONFIG["pit"],
        "tts_per": TTS_CONFIG["per"],
        "ai_background": ai_background,
        "wake_word": wake_word
    }

    mbti_descriptions = {
        "INTJ": "你是一个战略性、逻辑性强的人，擅长长期规划。",
        "INTP": "你是一个喜欢分析和探索概念的逻辑型思考者。",
        "ENTJ": "你是一个果断、擅长领导和组织的外向型人物。",
        "ENTP": "你是一个机智、喜欢辩论和新想法的探索者。",
        "INFJ": "你是一个理想主义者，关心他人并富有洞察力。",
        "INFP": "你是一个内省、富有同理心和想象力的人。",
        "ENFJ": "你是一个善于激励他人的领导者和沟通者。",
        "ENFP": "你是一个外向、富有创造力和同理心的人，喜欢探索新想法。",
        "ISTJ": "你是一个可靠、负责、注重细节的现实主义者。",
        "ISFJ": "你是一个乐于助人、重视和谐的守护者。",
        "ESTJ": "你是一个务实、善于管理和组织的领导者。",
        "ESFJ": "你是一个善于合作、关心他人的社交型人物。",
        "ISTP": "你是一个动手能力强、喜欢探索实际解决方案的人。",
        "ISFP": "你是一个温柔、富有创造力和艺术感的人。",
        "ESTP": "你是一个行动导向、喜欢冒险和尝试新事物的人。",
        "ESFP": "你是一个外向、喜欢表演和享受生活的乐观者。"
    }

    def save_params():
        nonlocal root
        global ai_background, wake_word, waiting_for_wakeup, conversation_history

        VAD_CONFIG["mode"] = int(vad_mode_slider.get())
        VAD_CONFIG["silence_threshold"] = int(vad_silence_slider.get())
        VAD_CONFIG["loud_sound_frames"] = int(vad_loud_slider.get())
        TTS_CONFIG["vol"] = int(tts_vol_slider.get())
        TTS_CONFIG["spd"] = int(tts_spd_slider.get())
        TTS_CONFIG["pit"] = int(tts_pit_slider.get())
        TTS_CONFIG["per"] = tts_per_var.get()

        new_background = ai_background_text.get("1.0", tk.END).strip()
        new_wake_word = wake_word_entry.get().strip()
        selected_mbti = mbti_var.get()

        background_changed = new_background != current_params["ai_background"]
        wake_word_changed = new_wake_word != current_params["wake_word"] and new_wake_word

        if wake_word_changed:
            wake_word = new_wake_word

        if selected_mbti:
            ai_background = mbti_descriptions[selected_mbti] + "\n" + new_background
            conversation_history.clear()
            waiting_for_wakeup = True
        elif background_changed:
            ai_background = new_background
            conversation_history.clear()
            if not waiting_for_wakeup:
                waiting_for_wakeup = True

        messages = []
        if selected_mbti:
            messages.append(f"人格已设定为：{selected_mbti}")
        if background_changed:
            messages.append("AI背景设定已更新，对话已重置")
        if wake_word_changed:
            messages.append(f"唤醒词已更新为：{new_wake_word}")
        if not messages:
            messages.append("参数已保存")

        messagebox.showinfo("成功", "\n".join(messages))
        root.destroy()

    def cancel_params():
        root.destroy()

    wake_word_frame = ttk.LabelFrame(scrollable_frame, text="唤醒词设置", padding=(10, 5))
    wake_word_frame.pack(fill=tk.X, padx=20, pady=(15, 5))
    ttk.Label(wake_word_frame, text="当前唤醒词：").grid(row=0, column=0, sticky=tk.W, pady=8, padx=(0, 10))
    wake_word_entry = ttk.Entry(wake_word_frame, width=30)
    wake_word_entry.grid(row=0, column=1, sticky=tk.W, pady=8)
    wake_word_entry.insert(0, current_params["wake_word"])

    ai_frame = ttk.LabelFrame(scrollable_frame, text="AI背景设定", padding=(10, 5))
    ai_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
    ai_background_text = scrolledtext.ScrolledText(ai_frame, height=5, wrap=tk.WORD)
    ai_background_text.pack(fill=tk.X, pady=(0, 10))
    ai_background_text.insert(tk.END, current_params["ai_background"])

    mbti_frame = ttk.LabelFrame(scrollable_frame, text="MBTI人格设定", padding=(10, 5))
    mbti_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
    ttk.Label(mbti_frame, text="请选择人格类型：").grid(row=0, column=0, sticky=tk.W, pady=8)
    mbti_var = tk.StringVar(value="")
    mbti_menu = ttk.OptionMenu(mbti_frame, mbti_var, "", *mbti_descriptions.keys())
    mbti_menu.grid(row=0, column=1, padx=10, sticky=tk.EW)

    vad_frame = ttk.LabelFrame(scrollable_frame, text="VAD语音检测配置", padding=(10, 5))
    vad_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
    ttk.Label(vad_frame, text="VAD灵敏度（0=低，3=高）：").grid(row=0, column=0, sticky=tk.W, pady=8)
    vad_mode_slider = ttk.Scale(vad_frame, from_=0, to=3, orient=tk.HORIZONTAL, value=current_params["vad_mode"])
    vad_mode_slider.grid(row=0, column=1, padx=10, sticky=tk.EW)

    ttk.Label(vad_frame, text="录音静音停止时间（帧，1帧=30ms）：").grid(row=1, column=0, sticky=tk.W, pady=8)
    vad_silence_slider = ttk.Scale(vad_frame, from_=50, to=200, orient=tk.HORIZONTAL, value=current_params["vad_silence"])
    vad_silence_slider.grid(row=1, column=1, padx=10, sticky=tk.EW)

    ttk.Label(vad_frame, text="中断播放的声音时长（帧，1帧=30ms）：").grid(row=2, column=0, sticky=tk.W, pady=8)
    vad_loud_slider = ttk.Scale(vad_frame, from_=VAD_CONFIG["min_loud_frames"], to=VAD_CONFIG["max_loud_frames"], orient=tk.HORIZONTAL, value=current_params["vad_loud"])
    vad_loud_slider.grid(row=2, column=1, padx=10, sticky=tk.EW)

    tts_frame = ttk.LabelFrame(scrollable_frame, text="TTS语音合成配置", padding=(10, 5))
    tts_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
    ttk.Label(tts_frame, text="音量（0-15）：").grid(row=0, column=0, sticky=tk.W, pady=8)
    tts_vol_slider = ttk.Scale(tts_frame, from_=0, to=15, orient=tk.HORIZONTAL, value=current_params["tts_vol"])
    tts_vol_slider.grid(row=0, column=1, padx=10, sticky=tk.EW)

    ttk.Label(tts_frame, text="语速（0-9）：").grid(row=1, column=0, sticky=tk.W, pady=8)
    tts_spd_slider = ttk.Scale(tts_frame, from_=0, to=9, orient=tk.HORIZONTAL, value=current_params["tts_spd"])
    tts_spd_slider.grid(row=1, column=1, padx=10, sticky=tk.EW)

    ttk.Label(tts_frame, text="语调（0-9）：").grid(row=2, column=0, sticky=tk.W, pady=8)
    tts_pit_slider = ttk.Scale(tts_frame, from_=0, to=9, orient=tk.HORIZONTAL, value=current_params["tts_pit"])
    tts_pit_slider.grid(row=2, column=1, padx=10, sticky=tk.EW)

    tts_per_options = {0: "度小鹿", 1: "度博文", 3: "度逍遥", 4: "度丫丫", 5: "度小娇"}
    ttk.Label(tts_frame, text="发音人：").grid(row=3, column=0, sticky=tk.W, pady=8)
    tts_per_var = tk.IntVar(value=current_params["tts_per"])
    tts_per_menu = ttk.OptionMenu(tts_frame, tts_per_var, current_params["tts_per"], *tts_per_options.keys())
    tts_per_menu.grid(row=3, column=1, padx=10, sticky=tk.EW)

    btn_frame = ttk.Frame(scrollable_frame, padding=(10, 5))
    btn_frame.pack(fill=tk.X, padx=20, pady=(15, 20))
    save_btn = ttk.Button(btn_frame, text="保存参数", command=save_params)
    save_btn.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
    cancel_btn = ttk.Button(btn_frame, text="取消（不保存）", command=cancel_params)
    cancel_btn.pack(side=tk.RIGHT, padx=20, fill=tk.X, expand=True)

    root.mainloop()


# --------------------------- 麦克风设备获取逻辑 ---------------------------
def get_default_microphone() -> int | None:
    """健壮获取麦克风设备，支持自动选择与兼容模式"""
    try:
        print("🔍 正在检测麦克风设备...")
        all_devices = sd.query_devices()  # 获取所有输入/输出设备
        input_devices = [dev for dev in all_devices if dev['max_input_channels'] > 0]

        if input_devices:
            print("\n📋 检测到以下麦克风设备：")
            for idx, dev in enumerate(input_devices):
                print(
                    f"   {idx + 1}. 设备名：{dev['name']} | 输入声道：{dev['max_input_channels']} | 设备ID：{dev['index']}")

            # 自动选择第一个可用麦克风
            default_mic_id = input_devices[0]['index']
            print(f"\n🎤 自动选择第一个麦克风：{input_devices[0]['name']}（设备ID：{default_mic_id}）")
            return default_mic_id
        else:
            print("⚠️  未查询到明确的输入设备，尝试使用系统默认模式")
            default_input = sd.default.device[0]  # 获取系统默认输入设备ID
            default_dev_info = sd.query_devices(default_input)
            if default_dev_info['max_input_channels'] > 0:
                print(f"🎤 使用系统默认麦克风（设备ID：{default_input}，名称：{default_dev_info['name']}）")
                return default_input
            else:
                print("⚠️  系统默认设备非麦克风，将使用自动适配模式")
                return None  # 不指定设备ID，让sounddevice自动处理
    except Exception as e:
        print(f"\n❌ 设备查询出错：{str(e)}")
        print("💡 已切换到兼容模式，尝试自动适配麦克风")
        return None


# 初始化麦克风
DEFAULT_MIC = get_default_microphone()


# --------------------------- 2. 配额管理工具 ---------------------------
def get_daily_char_usage() -> int:
    """获取当日TTS字符使用量"""
    if not os.path.exists(CHAR_COUNT_FILE):
        return 0
    today = time.strftime("%Y-%m-%d")
    with open(CHAR_COUNT_FILE, "r") as f:
        lines = f.readlines()
        if len(lines) >= 2 and lines[0].strip() == today:
            return int(lines[1].strip())
    return 0


def update_char_usage(added_chars: int) -> None:
    """更新当日TTS字符使用量"""
    today = time.strftime("%Y-%m-%d")
    current = get_daily_char_usage()
    new_total = current + added_chars
    with open(CHAR_COUNT_FILE, "w") as f:
        f.write(f"{today}\n{new_total}\n")
    # 显示更新后的配额使用情况（已改为999000字上限）
    print(f"📊 TTS字符使用：今日已用 {new_total}/{TTS_CONFIG['daily_char_limit']}")


def check_quota(text: str) -> bool:
    """检查TTS字符配额是否充足（上限已改为999000字）"""
    text_len = len(text)
    used = get_daily_char_usage()
    if used + text_len > TTS_CONFIG["daily_char_limit"]:
        print(f"❌ 配额不足！今日已用{used}字符，还需{text_len}字符（上限{TTS_CONFIG['daily_char_limit']}）")
        return False
    return True


# --------------------------- 3. 基础工具函数 ---------------------------
def get_baidu_token() -> str:
    """获取百度API访问Token"""
    url = (
        "https://aip.baidubce.com/oauth/2.0/token"
        f"?grant_type=client_credentials&client_id={ASR_CONFIG['api_key']}&client_secret={ASR_CONFIG['secret_key']}"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        print(f"❌ 获取Token失败：{str(e)}")
        return ""


def record_wav_16k(out_wav="recorded.wav") -> str | None:
    """录音函数（16kHz单声道），支持设备兼容与重试机制"""
    vad = webrtcvad.Vad(VAD_CONFIG["mode"])  # 使用最新VAD灵敏度
    RATE, CHANNELS, WIDTH = VAD_CONFIG["sample_rate"], 1, 2
    print("🎤 开始录音（停止说话指定时间后自动结束）...")

    audio_chunks = []
    silence_frame_count = 0
    max_retry = 3  # 录音失败重试次数
    retry_count = 0

    while retry_count < max_retry:
        try:
            # 构建流参数：有设备ID则指定，无则自动适配
            stream_kwargs = {
                "samplerate": RATE,
                "channels": CHANNELS,
                "dtype": np.int16
            }
            if DEFAULT_MIC is not None:
                stream_kwargs["device"] = DEFAULT_MIC

            with sd.InputStream(**stream_kwargs) as stream:
                while True:
                    chunk, overflow = stream.read(VAD_FRAME_SIZE)
                    if overflow:
                        print("⚠️  录音缓冲区溢出，部分数据可能丢失")

                    chunk_bytes = chunk.tobytes()
                    is_speech = vad.is_speech(chunk_bytes, RATE)

                    if is_speech:
                        audio_chunks.append(chunk)
                        silence_frame_count = 0
                        print(f"🔊 检测到语音... 静音计数: {silence_frame_count}/{VAD_CONFIG['silence_threshold']}",
                              end="\r")
                    else:
                        if audio_chunks:
                            audio_chunks.append(chunk)
                            silence_frame_count += 1
                            silence_sec = silence_frame_count * 0.03
                            print(
                                f"🟡 静音中... 计数: {silence_frame_count}/{VAD_CONFIG['silence_threshold']}（{silence_sec:.1f}秒后停止）",
                                end="\r")
                            if silence_frame_count >= VAD_CONFIG["silence_threshold"]:
                                print(f"\n🛑 检测到{silence_sec:.1f}秒静音，停止录音")
                                break
                        else:
                            print("🟡 等待语音输入...", end="\r")
            break  # 录音成功，跳出重试循环
        except sd.PortAudioError as e:
            retry_count += 1
            error_msg = str(e).lower()
            if "host error" in error_msg or "mme error" in error_msg:
                print(f"\n❌ 录音失败（{retry_count}/{max_retry}）：麦克风被占用或驱动错误")
                print("💡 建议：关闭微信、QQ等占用麦克风的程序")
            else:
                print(f"\n❌ 录音失败（{retry_count}/{max_retry}）：{str(e)}")
            if retry_count < max_retry:
                print("🔄 1秒后重试...")
                time.sleep(1)
        except Exception as e:
            print(f"\n❌ 录音异常：{str(e)}")
            return None

    if retry_count >= max_retry:
        print("❌ 多次重试失败，可能麦克风被占用或驱动异常")
        return None

    if not audio_chunks:
        print("❌ 未检测到有效语音，录音取消")
        return None

    # 保存录音文件
    audio_data = np.concatenate(audio_chunks, axis=0)
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(WIDTH)
        wf.setframerate(RATE)
        wf.writeframes(audio_data.tobytes())

    print(f"✅ 录音保存至：{out_wav}")
    return out_wav


def play_audio_with_interrupt(file_path: str) -> None:
    """播放音频，支持“较大声音中断”，使用扩大范围后的参数"""
    if not os.path.exists(file_path):
        print(f"❌ 音频文件不存在：{file_path}")
        return

    pygame.mixer.init()
    try:
        pygame.mixer.music.load(file_path)
        print(f"🔊 开始播放（检测到{VAD_CONFIG['loud_sound_frames'] * 0.03:.1f}秒声音可中断）：{file_path}")
        pygame.mixer.music.play()

        # 仅当获取到麦克风ID时，才监听较大声音以中断
        if DEFAULT_MIC is not None:
            vad = webrtcvad.Vad(VAD_CONFIG["mode"])  # 使用最新VAD灵敏度
            loud_frame_count = 0  # 连续语音帧计数器
            try:
                stream_kwargs = {
                    "samplerate": VAD_CONFIG["sample_rate"],
                    "channels": 1,
                    "dtype": np.int16,
                    "device": DEFAULT_MIC
                }
                with sd.InputStream(**stream_kwargs) as stream:
                    while pygame.mixer.music.get_busy():
                        chunk, _ = stream.read(VAD_FRAME_SIZE)
                        is_speech = vad.is_speech(chunk.tobytes(), VAD_CONFIG["sample_rate"])

                        if is_speech:
                            loud_frame_count += 1
                            loud_sec = loud_frame_count * 0.03
                            print(
                                f"🔍 检测到声音... 连续帧数: {loud_frame_count}/{VAD_CONFIG['loud_sound_frames']}（{loud_sec:.1f}秒）",
                                end="\r")
                            # 达到大声音阈值，停止播放（使用更新后的参数）
                            if loud_frame_count >= VAD_CONFIG["loud_sound_frames"]:
                                print(f"\n🔇 检测到{loud_sec:.1f}秒声音，停止播放")
                                pygame.mixer.music.stop()
                                break
                        else:
                            loud_frame_count = 0
                            print(f"🟡 播放中（等待{VAD_CONFIG['loud_sound_frames'] * 0.03:.1f}秒声音）...", end="\r")

                        time.sleep(0.01)
            except sd.PortAudioError as e:
                print(f"⚠️  监听声音失败（将继续播放）：{str(e)}")
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
        else:
            # 无麦克风ID时，仅普通播放（不支持中断）
            print("ℹ️  未指定麦克风，播放时不支持声音中断")
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)

        print("✅ 播放结束")
    except pygame.error as e:
        print(f"❌ 播放失败：{str(e)}")
    finally:
        pygame.mixer.quit()


# --------------------------- 4. 核心功能 ---------------------------
def speech_to_text(wav_path: str) -> str | None:
    """语音转文字（调用百度ASR）"""
    token = get_baidu_token()
    if not token:
        return None
    try:
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()
    except Exception as e:
        print(f"❌ 读取音频失败：{str(e)}")
        return None

    payload = {
        "format": "wav", "rate": 16000, "channel": 1, "token": token,
        "cuid": "python-voice-assistant", "speech": base64.b64encode(audio_bytes).decode(),
        "len": len(audio_bytes), "dev_pid": ASR_CONFIG["dev_pid"]
    }
    try:
        response = requests.post(
            ASR_CONFIG["url"], headers={"Content-Type": "application/json"},
            json=payload, timeout=15
        )
        data = response.json()
        if data.get("err_no") == 0:
            text = data["result"][0].strip()
            print(f"✅ ASR识别结果：{text}")
            return text
        print(f"❌ ASR识别失败：{data}")
        return None
    except Exception as e:
        print(f"❌ ASR请求失败：{str(e)}")
        return None


def text_to_speech(text: str, out_file: str = TTS_CONFIG["default_out"]) -> str | None:
    """文字转语音（调用百度TTS，使用最新TTS参数）"""
    # 过滤特殊字符，避免TTS接口报错
    for char in ['#', '&', '@', '!', '*', ';']:
        text = text.replace(char, '')
    # 限制单条文本长度（兼顾配额与接口限制，上限已改为999000字）
    max_len = min(120, TTS_CONFIG["daily_char_limit"] - get_daily_char_usage())
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."
        print(f"⚠️  文本截断：{text}")
    if not text:
        print("❌ 无有效文本")
        return None
    if not check_quota(text):
        return None

    try:
        # 使用面板调节后的TTS参数（音量、语速、语调、发音人）
        result = tts_client.synthesis(
            text, lang="zh", ctp=1,
            options={
                "vol": TTS_CONFIG["vol"],
                "spd": TTS_CONFIG["spd"],
                "pit": TTS_CONFIG["pit"],
                "per": TTS_CONFIG["per"]
            }
        )
        if isinstance(result, dict):
            print(f"❌ TTS失败：{result.get('err_msg')}")
            if "limit reached" in result.get("err_msg", "").lower():
                print("💡 需购买资源包或次日重置配额")
            return None
        # 保存TTS音频文件
        with open(out_file, "wb") as f:
            f.write(result)
        update_char_usage(len(text))
        print(f"✅ TTS保存至：{out_file} | 文本：{text}")
        return out_file
    except Exception as e:
        print(f"❌ TTS请求失败：{str(e)}")
        return None


def call_chat_api(prompt: str) -> str | None:
    """调用本地聊天API，支持对话历史记忆和AI背景设定"""
    global conversation_history, ai_background

    if not prompt:
        print("❌ 无对话内容")
        return None

    # 构建提示信息，包含AI背景设定
    system_prompt = ""
    if ai_background:
        system_prompt = f"以下是你的背景设定，请严格遵守：{ai_background}\n\n"

    # 构建包含历史记录的完整对话
    full_conversation = "\n".join([
        f"用户: {item['user']}\nAI: {item['ai']}"
        for item in conversation_history
    ])

    # 拼接系统提示、历史对话与当前查询
    if full_conversation:
        full_prompt = f"{system_prompt}{full_conversation}\n用户: {prompt}\nAI:"
    else:
        full_prompt = f"{system_prompt}用户: {prompt}\nAI:"

    # 调用本地Chat API
    url = "http://localhost:8000/chat/"
    data = {
        "prompt": full_prompt,
        "options": {"temperature": 0.7, "max_tokens": 200}
    }

    try:
        response = requests.post(url, json=data, timeout=20)
        response.raise_for_status()
        reply = response.json().get("response", "").strip()
        print(f"✅ Chat回复：{reply}")
        return reply
    except Exception as e:
        print(f"❌ Chat请求失败：{str(e)}")
        return None


def test_health_api() -> None:
    """测试本地API健康状态"""
    url = "http://localhost:8000/health"
    try:
        response = requests.get(url, timeout=5)
        print(f"✅ 健康检查：{response.json()}")
    except Exception as e:
        print(f"❌ 健康检查失败：{str(e)}")


# --------------------------- 5. 业务流程（使用动态唤醒词） ---------------------------
def wake_up_detect() -> bool:
    """唤醒检测：使用可配置的唤醒词"""
    global conversation_history, waiting_for_wakeup, input_mode, wake_word

    # 进入唤醒等待状态时，重置为语音输入并清空历史记录
    if waiting_for_wakeup:
        with mode_lock:
            input_mode = "voice"  # 唤醒时默认使用语音输入
        conversation_history = []
        print("🧹 已清空历史记录，等待新的唤醒...")

    print(f"\n🔍 等待唤醒词（{wake_word}），停止说话指定时间后自动录音结束...")
    wav_file = record_wav_16k(out_wav="wake_up.wav")
    if not wav_file:
        return False

    recognized_text = speech_to_text(wav_file)
    if recognized_text and wake_word in recognized_text:
        # 如果有AI背景设定，提示用户
        if ai_background:
            print(f"✅ 检测到唤醒词：{wake_word}（当前AI背景设定已生效）")
        else:
            print(f"✅ 检测到唤醒词：{wake_word}")
        waiting_for_wakeup = False
        return True

    print(f"❌ 未检测到唤醒词（识别结果：{recognized_text or '无'}，唤醒词：{wake_word}）")
    return False


def voice_interaction_flow() -> None:
    """完整语音交互流程：支持动态唤醒词和扩展的中断时长设置"""
    global waiting_for_wakeup, input_mode, conversation_history, ai_background, show_control_panel, wake_word

    print("=" * 50)
    print(f"🎯 语音助手启动：当前唤醒词为「{wake_word}」（可在控制面板修改）")
    print(f"🎯 TTS每日配额：{TTS_CONFIG['daily_char_limit']}字")
    print("=" * 50)

    # 设置模式切换监听器
    setup_mode_switch_listener()

    # 提示麦克风适配状态
    if DEFAULT_MIC is None:
        print("⚠️  未明确指定麦克风设备，将尝试自动适配（可能影响录音稳定性）")
        print("💡 建议：检查麦克风驱动或关闭占用麦克风的程序\n")

    # 主循环：持续运行
    while True:
        # 1. 等待唤醒（未唤醒时循环检测）
        while not wake_up_detect():
            time.sleep(0.5)

        # 2. 唤醒成功：进入对话模式
        print("\n🎉 唤醒成功！支持指令：")
        print(f"   - 唤醒词：当前为「{wake_word}」（可在控制面板修改）")
        print("   - 正常对话：直接说话提问")
        print("   - 打开控制面板：说【控制面板】或按Alt键")
        print("   - 返回唤醒：说【再见】")
        print("   - 切换输入模式：按Enter键(文字)/Tab键(语音)")
        print(f"ℹ️ TTS每日配额：{get_daily_char_usage()}/{TTS_CONFIG['daily_char_limit']}字")

        # 显示当前AI背景设定状态
        if ai_background:
            print(f"ℹ️ 当前AI背景设定：{ai_background[:50]}{'...' if len(ai_background) > 50 else ''}")

        print("💡 提示：当前输入模式 - " + (
            "文字输入（按Tab返回语音）" if input_mode == "text" else "语音输入（按Enter切换文字）\n"))

        # 3. 对话循环（唤醒后持续交互）
        while not waiting_for_wakeup:
            # 检查是否需要打开控制面板（Alt键触发）
            if show_control_panel:
                show_control_panel = False  # 重置标记
                print(f"🔧 准备打开控制面板...")
                # 播放提示音
                panel_audio = text_to_speech("正在为您打开参数控制面板，请在窗口中调节参数。", "panel_notify.mp3")
                if panel_audio:
                    play_audio_with_interrupt(panel_audio)
                # 打开控制面板（阻塞直到用户关闭窗口）
                create_control_panel()

                # 控制面板关闭后，显示当前唤醒词
                print(f"ℹ️ 当前唤醒词已更新为：「{wake_word}」")

                # 如果面板关闭后处于唤醒状态，说明可能更改了背景设定，需要重新唤醒
                if waiting_for_wakeup:
                    # 提示用户需要重新唤醒
                    wakeup_again_audio = text_to_speech(f"AI已重置，请说{wake_word}重新唤醒。", "wakeup_again.mp3")
                    if wakeup_again_audio:
                        play_audio_with_interrupt(wakeup_again_audio)
                    break

                # 面板关闭后提示
                after_panel_audio = text_to_speech("参数面板已关闭，可继续正常对话。", "after_panel.mp3")
                if after_panel_audio:
                    play_audio_with_interrupt(after_panel_audio)
                continue

            current_mode = input_mode  # 保存当前模式，避免在处理过程中模式被切换

            # 根据当前模式获取用户输入
            if current_mode == "text":
                # 文字输入模式
                user_text = get_text_input("请输入文字（按Cancel返回语音输入）: ")
                if not user_text:  # 用户取消输入
                    with mode_lock:
                        input_mode = "voice"
                    print("🎤 已切换到语音输入模式")
                    continue
                print(f"💬 用户（文字输入）：{user_text}")
            else:
                # 语音输入模式
                user_audio = record_wav_16k("user_command.wav")
                if not user_audio:
                    continue

                user_text = speech_to_text(user_audio)
                if not user_text:
                    # 未听清时提示重试
                    retry_audio = text_to_speech("我没听清，请再说一遍~", "retry.mp3")
                    if retry_audio:
                        play_audio_with_interrupt(retry_audio)
                    continue

            # 指令分支判断
            # 分支1：打开控制面板（语音指令）
            if "控制面板" in user_text:
                print(f"🔧 收到指令：{user_text} → 启动参数面板")
                # 播放提示音
                panel_audio = text_to_speech("正在为您打开参数控制面板，请在窗口中调节参数。", "panel_notify.mp3")
                if panel_audio:
                    play_audio_with_interrupt(panel_audio)
                # 打开控制面板（阻塞直到用户关闭窗口）
                create_control_panel()

                # 控制面板关闭后，显示当前唤醒词
                print(f"ℹ️ 当前唤醒词已更新为：「{wake_word}」")

                # 如果面板关闭后处于唤醒状态，说明可能更改了背景设定，需要重新唤醒
                if waiting_for_wakeup:
                    # 提示用户需要重新唤醒
                    wakeup_again_audio = text_to_speech(f"AI已重置，请说{wake_word}重新唤醒。", "wakeup_again.mp3")
                    if wakeup_again_audio:
                        play_audio_with_interrupt(wakeup_again_audio)
                    break

                # 面板关闭后提示
                after_panel_audio = text_to_speech("参数面板已关闭，可继续正常对话。", "after_panel.mp3")
                if after_panel_audio:
                    play_audio_with_interrupt(after_panel_audio)
                continue

            # 分支2：返回唤醒状态
            elif "再见" in user_text:
                print(f"👋 收到返回指令：{user_text}")
                exit_audio = text_to_speech(f"已返回唤醒等待状态，说{wake_word}继续交流。", "exit.mp3")
                if exit_audio:
                    play_audio_with_interrupt(exit_audio)
                waiting_for_wakeup = True
                break

            # 分支3：正常对话（调用Chat API）
            else:
                chat_reply = call_chat_api(user_text)
                if not chat_reply:
                    # 回复失败时提示
                    no_reply_audio = text_to_speech("抱歉，暂时无法回复，请稍后再试。", "no_reply.mp3")
                    if no_reply_audio:
                        play_audio_with_interrupt(no_reply_audio)
                    continue

                # 保存对话历史（限制10轮，避免内存占用过高）
                conversation_history.append({
                    "user": user_text,
                    "ai": chat_reply
                })
                if len(conversation_history) > 10:
                    conversation_history = conversation_history[-10:]
                print(f"📝 已保存对话历史（共{len(conversation_history)}轮）")

                # 播放AI回复（使用最新TTS参数）
                print(f"🤖 AI：{chat_reply}")
                reply_audio = text_to_speech(chat_reply, "chat_reply.mp3")
                if reply_audio:
                    play_audio_with_interrupt(reply_audio)

            # 提示后续操作
            print("\n" + "-" * 30)
            print(f"💡 唤醒词：「{wake_word}」（可在控制面板修改）")
            print("💡 可继续操作：说问题/说控制面板/按Alt键/再见")
            print(f"💡 当前输入模式：{input_mode}（按Enter切换文字，按Tab切换语音）")
            print(
                f"💡 TTS配额剩余：{TTS_CONFIG['daily_char_limit'] - get_daily_char_usage()}/{TTS_CONFIG['daily_char_limit']}字")
            print("-" * 30 + "\n")


# --------------------------- 6. 执行入口 ---------------------------
if __name__ == "__main__":
    test_health_api()  # 启动时测试API健康状态
    try:
        voice_interaction_flow()  # 启动交互流程
    except KeyboardInterrupt:
        print("\n🔌 程序被手动中断")
    finally:
        # 清理临时音频文件
        for tmp_file in ["wake_up.wav", "user_command.wav", "chat_reply.mp3", "retry.mp3",
                         "no_reply.mp3", "exit.mp3", "panel_notify.mp3", "after_panel.mp3", "wakeup_again.mp3"]:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        print("🗑️  临时文件已清理")
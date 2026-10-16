# -*- coding: utf-8 -*-
"""
Zotero Picker 后端服务
版权所有 © 2025 四川大学华西医院
主要作者：肖青 Qing Xiao
软件著作权登记号：2025SR0813220
本软件受《中华人民共和国著作权法》保护，未经授权禁止复制、修改、发布或用于商业用途。
"""

from flask import Flask, request, jsonify
import sqlite3
import os
import requests
import logging
from flask_cors import CORS
import json
import time
import re
import shutil
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sys
import html

app = Flask(__name__)
CORS(app)

# Zotero 数据库活快照状态
# 【2026-10 新增】原实现用 mode=ro&immutable=1 打开 zotero.sqlite，该模式会完全
# 忽略 -wal 文件，导致读到"删除操作还没落盘"的过期数据：用户在 Zotero 删掉文献后，
# 网页仍显示"已存在"，且跳转链接指向已失效的 itemKey。
# 现改为复制 db+wal 生成活快照，并以 (mtime_ns, size) 作为失效签名。
_snapshot_lock = threading.Lock()
_snapshot_state = {'sig': None, 'path': ''}

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'zotero_service.log'))
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

def get_exe_directory():
    """获取exe文件所在目录"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe文件
        return os.path.dirname(sys.executable)
    else:
        # 如果是源码运行
        return os.path.dirname(os.path.abspath(__file__))

def load_config():
    """加载配置文件"""
    # 配置文件放在exe同目录下
    exe_dir = get_exe_directory()
    config_path = os.path.join(exe_dir, 'zotero_config.json')
    
    default_paths = {
        'windows': str(Path.home() / 'Zotero' / 'zotero.sqlite'),
        'linux': str(Path.home() / '.zotero' / 'zotero' / 'zotero.sqlite'),
        'darwin': str(Path.home() / 'Zotero' / 'zotero.sqlite')
    }
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"成功加载配置文件: {config_path}")
                return config
        else:
            # 创建默认配置文件
            default_config = {
                'db_path': default_paths.get(sys.platform, default_paths['windows']),
                'description': '配置说明：db_path 为 Zotero 数据库文件路径，可手动修改此路径',
                'version': '1.0'
            }
            save_config(default_config)
            logger.info(f"创建默认配置文件: {config_path}")
            return default_config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return {'db_path': default_paths.get(sys.platform, default_paths['windows'])}

def save_config(config):
    """保存配置文件"""
    exe_dir = get_exe_directory()
    config_path = os.path.join(exe_dir, 'zotero_config.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"配置文件已保存: {config_path}")
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")

def get_db_path():
    """获取当前的数据库路径"""
    if not hasattr(get_db_path, '_db_path'):
        config = load_config()
        get_db_path._db_path = config.get('db_path', '')
    return get_db_path._db_path

def set_db_path(path):
    """设置当前的数据库路径"""
    get_db_path._db_path = path
    config = load_config()
    config['db_path'] = path
    save_config(config)

def create_high_dpi_dialog():
    """创建高DPI支持的对话框"""
    root = tk.Tk()
    root.withdraw()
    
    # 设置高DPI支持
    try:
        import ctypes
        # 设置DPI感知
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        # 获取缩放因子
        scale_factor = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
    except:
        scale_factor = 1.0
    
    # 应用缩放因子到字体大小
    base_font_size = int(10 * scale_factor)
    title_font_size = int(12 * scale_factor)
    
    return root, scale_factor, base_font_size, title_font_size

def select_database_path(use_default=False):
    """选择数据库路径"""
    try:
        logger.info("开始选择数据库路径...")
        root, scale_factor, base_font_size, title_font_size = create_high_dpi_dialog()
        
        config = load_config()
        current_path = config.get('db_path', '')
        logger.info(f"当前配置的路径: {current_path}")
        
        # 如果配置文件中没有有效路径，直接打开文件选择器
        if not use_default or not current_path or not os.path.exists(current_path):
            logger.info("配置文件中无有效路径，直接打开文件选择器")
            root.destroy()
            
            file_root = tk.Tk()
            file_root.withdraw()
            initial_dir = str(Path(current_path).parent) if current_path else str(Path.home())
            file_path = filedialog.askopenfilename(
                title='选择 Zotero 数据库文件 (zotero.sqlite)',
                initialfile='zotero.sqlite',
                initialdir=initial_dir,
                filetypes=[('SQLite数据库', '*.sqlite'), ('所有文件', '*.*')]
            )
            file_root.destroy()
            
            if file_path and os.path.exists(file_path):
                config['db_path'] = file_path
                save_config(config)
                logger.info(f"用户选择新路径并保存: {file_path}")
                return file_path
            else:
                logger.warning("用户未选择有效文件")
                return None
        
        # 配置文件中有有效路径，显示倒计时对话框
        dialog = tk.Toplevel(root)
        dialog.title("Zotero Picker - 数据库配置")
        
        # 根据缩放因子调整窗口大小
        window_width = int(700 * scale_factor)
        window_height = int(450 * scale_factor)
        dialog.geometry(f"{window_width}x{window_height}")
        
        # 窗口居中
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        dialog.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        dialog.lift()
        dialog.attributes('-topmost', True)
        dialog.resizable(False, False)
        
        # 设置窗口样式
        style = ttk.Style()
        style.theme_use('clam')
        
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(
            main_frame, 
            text="Zotero 数据库配置", 
            font=('Microsoft YaHei UI', title_font_size, 'bold')
        )
        title_label.pack(pady=(0, 15))
        
        exe_dir = get_exe_directory()
        config_file_path = os.path.join(exe_dir, 'zotero_config.json')
        
        message = (
            "检测到配置文件中的数据库路径：\n\n"
            f"📂 {current_path}\n\n"
            "如需修改路径，请在倒计时结束前点击相应按钮。\n\n"
            "常见位置参考：\n"
            "• Windows: %USERPROFILE%\\Zotero\\zotero.sqlite\n"
            "• Linux: ~/.zotero/zotero/zotero.sqlite\n"
            "• macOS: ~/Zotero/zotero.sqlite\n\n"
            f"💡 提示：您也可以直接编辑配置文件：\n{config_file_path}"
        )
        
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        message_text = tk.Text(
            text_frame, height=13, wrap=tk.WORD,
            font=('Microsoft YaHei UI', base_font_size),
            relief=tk.FLAT, bg=dialog.cget('bg'),
            cursor='arrow', state=tk.DISABLED
        )
        message_text.pack(fill=tk.BOTH, expand=True)
        
        message_text.config(state=tk.NORMAL)
        message_text.insert(tk.END, message)
        message_text.config(state=tk.DISABLED)
        
        countdown_frame = ttk.Frame(main_frame)
        countdown_frame.pack(pady=10)
        
        countdown_label = ttk.Label(
            countdown_frame, 
            text="5秒后自动使用配置路径",
            font=('Microsoft YaHei UI', base_font_size, 'bold'),
            foreground='red'
        )
        countdown_label.pack()
        
        # ==================== 核心修复逻辑开始 ====================
        result = {'path': current_path}
        state = {'timer_id': None}  # 用一个字典保存定时器句柄，方便随时取消
        
        def safe_quit():
            """安全退出机制：取消所有残余定时器并结束主循环"""
            if state['timer_id']:
                dialog.after_cancel(state['timer_id'])
                state['timer_id'] = None
            root.quit()  # 安全结束 mainloop
        
        def choose_new_path():
            # 用户点击选择时，必须先挂起倒计时！
            if state['timer_id']:
                dialog.after_cancel(state['timer_id'])
                state['timer_id'] = None
                if countdown_label.winfo_exists():
                    countdown_label.config(text="倒计时已暂停...")
            
            initial_dir = str(Path(current_path).parent) if current_path else str(Path.home())
            file_path = filedialog.askopenfilename(
                title='选择 Zotero 数据库文件',
                initialfile='zotero.sqlite',
                initialdir=initial_dir,
                filetypes=[('SQLite数据库', '*.sqlite'), ('所有文件', '*.*')]
            )
            if file_path:
                result['path'] = file_path
                config['db_path'] = file_path
                save_config(config)
                logger.info(f"用户选择新路径并保存: {file_path}")
            
            safe_quit()
        
        def use_config_path():
            result['path'] = current_path
            safe_quit()
            
        def open_config_folder():
            try:
                if sys.platform == "win32":
                    os.startfile(exe_dir)
                elif sys.platform == "darwin":
                    os.system(f"open '{exe_dir}'")
                else:
                    os.system(f"xdg-open '{exe_dir}'")
            except Exception as e:
                messagebox.showerror("错误", f"无法打开文件夹: {e}")
        
        def update_countdown(count):
            if count > 0:
                # 必须检查组件是否存活，防止抛出隐式异常
                if countdown_label.winfo_exists():
                    countdown_label.config(text=f"{count}秒后自动使用配置路径")
                    # 保存定时器句柄到 state 中
                    state['timer_id'] = dialog.after(1000, update_countdown, count - 1)
            else:
                use_config_path()
        # ==================== 核心修复逻辑结束 ====================

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=15)
        
        button_width = 15
        ttk.Button(button_frame, text="选择新路径", command=choose_new_path, width=button_width).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="使用配置路径", command=use_config_path, width=button_width).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="打开配置文件夹", command=open_config_folder, width=button_width).pack(side=tk.LEFT, padx=5)
        
        copyright_frame = ttk.Frame(main_frame)
        copyright_frame.pack(side=tk.BOTTOM, pady=(15, 0))
        ttk.Label(
            copyright_frame,
            text="© 2025 四川大学华西医院 · 作者：肖青 · 登记号：2025SR0813220",
            font=('Microsoft YaHei UI', int(8 * scale_factor)),
            foreground='gray'
        ).pack()
        
        # 绑定右上角X按钮的关闭事件
        dialog.protocol("WM_DELETE_WINDOW", use_config_path)
        
        # 启动倒计时
        update_countdown(5)
        
        # 替代原本脆弱的 dialog.wait_window()，使用稳如磐石的 mainloop
        root.mainloop()
        
        # 当 root.quit() 被调用后，代码才会执行到这里，此时进行彻底的清理工作
        dialog.destroy()
        root.update()  # 强行冲刷掉操作系统队列中可能残留的所有重绘/定时事件
        root.destroy()
        
        logger.info(f"最终选择的路径: {result['path']}")
        return result['path']
        
    except Exception as e:
        logger.exception("选择数据库路径时出错")
        raise

def get_zotero_headers():
    """
    返回访问 Zotero 本地服务所需的安全请求头。

    【Zotero 7+ 关键约束，勿改】
    - 不得使用 "Mozilla/" 开头的 User-Agent：Zotero 7 起对"疑似浏览器请求"
      （UA 以 Mozilla/ 开头，或带 Origin 头）执行防 DNS rebinding 防护，
      直接 _cancelResponse() 断连、不返回任何响应。这是 Zotero 升级后
      通讯失败的根因。
    - 必须带 "X-" 前缀的 X-Zotero-Connector-API-Version；旧的无前缀头无效，
      且版本必须 >= 3，否则 saveItems 返回 400 CONNECTOR_VERSION_OUTDATED。
    """
    return {
        'Content-Type': 'application/json',
        'User-Agent': 'ZoteroPickerBackend/1.0',
        'X-Zotero-Connector-API-Version': '3'
    }


def filter_alive_item_keys(item_keys, key_lib_map=None, conn=None):
    """
    用 Zotero HTTP API 权威复核 itemKey 是否仍然存活（未进回收站、未被删）。

    为什么需要这层：
    sqlite 快照与 Zotero 内存状态之间存在 TOCTOU 窗口——查到结果后、用户点击
    跳转前，条目可能已被删除。此时网页仍会显示"已存在"，而zotero://select/items/
    跳转链接会提示找不到条目。这里用在线 API 做二次确认，只保留真实存活的 key。

    【2026-10 修复·重要】原实现固定查 /api/users/0/items（只含个人文库）。
    但 Zotero 库里还有群组库（type=group，本库 449 条）和多个 feed 库
    （type=feed，本库 82 条），它们的条目 itemKey 在 users/0 下**查不到**，
    于是被当作"已失效"整批剔除 —— 表现为"这些文献明明在库里，网页却显示
    不在库中，点击添加反而能跳转"（Zotero 保存时按 users/0 落库）。
    现在按 libraryID 分别路由：个人库 → users/0，群组库 → groups/{groupID}。

    【feed 库无法复核，实测】Zotero 10 本地 API **没有 feed 端点**
    （GET /api/feeds/3/items 返回 404 "No endpoint found"），
    而 feed 库条目也不在 users/0 下。因此 feed 库条目直接跳过复核、
    一律按"存活"处理——总比把在库条目误杀成"不在库中"要好。

    参数：
      item_keys  : 待复核的 itemKey 列表
      key_lib_map: {itemKey: libraryID}，由调用方提供（sqlite 查询里已有该列）
      conn       : 可选，用于在未提供映射时自行读取库类型

    返回：存活 key 的集合。
    某次请求失败时**不**把该 key 判死（保守保留），因为误杀比漏删更糟。
    """
    keys = [k for k in dict.fromkeys(item_keys) if k]
    if not keys:
        return set()

    headers = get_zotero_headers()
    # 【性能】必须把 127.0.0.1 放在 localhost 之前：
    # 本机 localhost 会先解析到 IPv6 ::1，而 Zotero 只监听 IPv4，
    # 导致每次请求先等 IPv6 超时再回退 IPv4，实测 2.1s vs 0.08s（差 26 倍）。
    bases = ['http://127.0.0.1:23119', 'http://localhost:23119']

    # libraryID -> API 路径前缀映射（群组库与 feed 库必须区别对待）
    key_to_base = {}
    lib_types = {}
    if conn is not None:
        try:
            rows = conn.execute(
                "SELECT l.libraryID, l.type, g.groupID "
                "FROM libraries l "
                "LEFT JOIN groups g ON g.libraryID = l.libraryID"
            ).fetchall()
            for r in rows:
                lid = r['libraryID']
                lib_types[lid] = r['type']
                if r['type'] == 'group' and r['groupID']:
                    key_to_base[lid] = f'/api/groups/{r["groupID"]}/items'
                elif r['type'] == 'feed':
                    # 本地 API 无 feed 端点（实测 404），映射留空表示"不可复核"
                    key_to_base[lid] = None
                else:
                    key_to_base[lid] = '/api/users/0/items'
        except Exception as e:
            logger.warning(f'读取库类型失败，全部按个人文库复核: {e}')
            key_to_base = {}
            lib_types = {}

    # 决定每个 key 该查哪个 API：优先用调用方给的 libraryID
    def path_for(ikey):
        lid = (key_lib_map or {}).get(ikey)
        if lid is not None and lid in key_to_base:
            return key_to_base[lid]
        # 映射缺失或未知：若该 key 明确属于非个人库，直接跳过复核（保守保留）
        if lid is not None and lib_types.get(lid) in ('group', 'feed'):
            return None
        return '/api/users/0/items'

    # 同一路径的多个 key 合并成一次请求，减少 HTTP 往返
    batches = {}
    uncheckable = []
    for k in keys:
        p = path_for(k)
        if p is None:
            uncheckable.append(k)
            continue
        batches.setdefault(p, []).append(k)

    if uncheckable:
        logger.info(f"{len(uncheckable)} 个条目属于群组/feed 库且未建立 API 映射，跳过复核并保留")

    alive = set()
    failed_paths = set()
    for path, ks in batches.items():
        done = False
        for base in bases:
            full = f'{base}{path}'
            if full in failed_paths:
                continue
            try:
                # Zotero 的 itemKey 参数支持逗号分隔批量查询
                resp = requests.get(
                    full,
                    params={'itemKey': ','.join(ks), 'limit': len(ks) * 5 + 10},
                    headers=headers,
                    timeout=10
                )
                if not resp.ok:
                    logger.warning(
                        f"API 复核 {path} 返回 HTTP {resp.status_code}，跳过该库"
                    )
                    failed_paths.add(full)
                    continue
                data = resp.json()
                alive.update(it['key'] for it in data if it.get('key'))
                done = True
                break
            except (requests.exceptions.RequestException, ValueError) as e:
                logger.warning(f"API 复核失败({full}): {e}")
                continue
        if not done:
            # 该库复核不通 → 保守保留，不做剔除
            logger.info(f"API 无法复核 {path}，保留该批结果")
            alive.update(ks)

    # 未建立映射而跳过的 key 一律视为存活（保守：宁可多显示"已存在"）
    alive.update(uncheckable)
    return alive


def _db_file_signature(db_path):
    """
    生成数据库"版本签名"：主库与 WAL 的 (mtime_ns, size)。

    Zotero 采用 WAL 模式，写入先落 -wal 文件、稍后才 checkpoint 回主库。
    只要 -wal 的 mtime 或大小变化，就说明有新的写入（含删除）发生，
    必须重新生成快照，否则读到的是过期数据。

    【真实故障案例，2026-10】
    主库 mtime 停在 11:09、-wal mtime 为 11:15，此时旧代码用
    immutable=1 打开（完全忽略 WAL），读到 items=13163/deletedItems=12，
    而真实库是 items=13151/deletedItems=2 —— 10 条删除操作全压在 WAL 里。
    表现为"库里已删除文献，网页仍显示已存在；点击跳转提示找不到条目"。
    """
    parts = []
    for suffix in ('', '-wal'):
        p = db_path + suffix
        try:
            st = os.stat(p)
            parts.append((st.st_mtime_ns, st.st_size))
        except OSError:
            parts.append(None)
    return tuple(parts)


def _signature_key(sig):
    """把 (主库签名, WAL签名) 压成一个短字符串，作为快照文件名的唯一标识。

    【为什么必须把 WAL 也算进去】
    Zotero 采用 WAL 模式：所有写入先追加到 zotero.sqlite-wal，
    主库文件只在 checkpoint 时才被改写（甚至可能连续数天不变）。
    若文件名只由主库签名决定，则 WAL 变化时文件名不变，
    `os.path.exists(dest)` 恒为 True，复制逻辑整段被跳过 —— 快照永不更新。
    这正是"库里已添加文献、网页却显示不在库中"的根因（2026-10-16 实锤）。
    """
    parts = []
    for item in sig:
        parts.append('x' if item is None else f'{item[0]}_{item[1]}')
    return '-'.join(parts)


def _refresh_live_snapshot(db_path):
    """
    把 zotero.sqlite + zotero.sqlite-wal 复制到临时目录，得到一份"活快照"。

    为什么必须拷贝：
      - mode=ro&immutable=1  → 忽略 WAL，读到过期快照（本故障根因）
      - mode=ro（不加 immutable）→ Zotero 持有写锁，报 "database is locked"
      - nolock=1              → 无法打开
    实测只复制 db+wal（不复制 -shm，让 sqlite 自行做 WAL 恢复）即可拿到
    与 Zotero API 完全一致的数据，且不干扰 Zotero 运行（纯只读复制）。

    实现要点：
    - 用带签名的版本化文件名，**不做覆盖式改名**。
      Windows 上 os.replace 覆盖已存在文件会因文件被占用/权限而失败
      （实测 WinError 5拒绝访问），版本化命名完全避开该问题。
    - WAL 与主库必须同名成对（.sqlite / .sqlite-wal），否则 sqlite 认为没有 WAL，
      会读到尚未 checkpoint 的过期数据（本项目实际踩过这个坑）。
    - 旧版本文件在成功切换后再清理，避免并发读时被删。
    - **绝不能留下 -shm**：sqlite 打开快照时会发现同目录存在配套 -shm，
      便认定"WAL 已恢复完毕"，直接跳过 WAL 重放、也**不会**在读完后把
      快照的 -wal 清零。上一轮运行遗留的 -shm 会让后续所有读取跳过 WAL 恢复，
      于是"复制进来的 WAL 明明有内容却读不到"（2026-10-16 实测：
      快照 -wal 为 0 字节且读不到 WAL 里的新条目）。故每次切换快照前
      都要把 -shm 一并清掉，强制 sqlite 走完整恢复流程。
    """
    snap_dir = os.path.join(tempfile.gettempdir(), 'zotero_picker_live')
    try:
        os.makedirs(snap_dir, exist_ok=True)
    except OSError:
        # 退到用户目录（打包 exe 时 TEMP 可能不可写）
        snap_dir = os.path.join(os.path.expanduser('~'), '.zotero_picker_live')
        os.makedirs(snap_dir, exist_ok=True)

    # 【2026-10 修复·关键】文件名必须由 **主库 + WAL 的联合签名** 决定，
    # 不能只看主库 mtime。
    # 缺陷复盘：Zotero 的日常写入（新增/删除/改字段）全部先落 -wal，主库文件
    # 本身可能几天都不变（checkpoint 才写主库）。原实现用主库 mtime_ns 当戳，
    # 于是 Zotero 改了一整天库，dest 名字也纹丝不动；下一次进来
    # `if not os.path.exists(dest)` 直接命中旧文件、整段复制被跳过 →
    # 快照永久冻结在某个历史时刻。
    # 实测（2026-10-16）：主库 mtime 停在 13:12、WAL mtime 已到 13:22，
    # 真实库比快照多出 1 条新文献（10.1162/neco_a_00442），后端却报
    # exists=False —— 网页显示"不在库中"，而 Zotero 里明明有。
    sig = _db_file_signature(db_path)
    sig_key = _signature_key(sig)
    dest = os.path.join(snap_dir, f'zotero_snapshot_{sig_key}.sqlite')

    # 完整性判定：源库此刻有 WAL 时，快照必须也有配套的 -wal，
    # 否则这份快照就是"只读主库"的残缺版本，会漏掉全部最新写入。
    # （签名相同却缺 WAL 的情形会出现在：上一轮生成时被 -shm 干扰、
    #   或 WAL 是在快照生成之后才出现。）
    src_has_wal = sig[1] is not None
    snap_wal = dest + '-wal'
    need_build = not os.path.exists(dest)
    if not need_build and src_has_wal:
        snap_wal_size = os.path.getsize(snap_wal) if os.path.exists(snap_wal) else -1
        # 源库 WAL 非空而快照 WAL 缺失或为 0 → 残缺，必须重建
        if sig[1][1] > 0 and snap_wal_size <= 0:
            need_build = True
            logger.info('快照缺失有效 WAL，重建快照')

    if need_build:
        # 【并发安全】复制主库+WAL 需要上百毫秒，期间 Zotero 仍在写 WAL，
        # 可能拷到"主库旧 + WAL 新"的撕裂组合，或干脆拷到半个 WAL。
        # 这里做有限次重试：复制完成后重新取签名，与目标签名比对，
        # 不一致就丢弃重来，确保交出去的一定是自洽快照。
        for _attempt in range(3):
            tmp_dest = dest + '.tmp'
            try:
                for stale in (tmp_dest, tmp_dest + '-wal', tmp_dest + '-shm'):
                    if os.path.exists(stale):
                        try:
                            os.remove(stale)
                        except OSError:
                            pass

                shutil.copyfile(db_path, tmp_dest)
                wal = db_path + '-wal'
                if os.path.exists(wal):
                    # 必须连 WAL 一起复制；不复制 -shm，让 sqlite 用 WAL 日志自行恢复，
                    # 恢复后的结果与 Zotero 在线 API 一致（已实测 items/deletedItems 完全吻合）
                    shutil.copyfile(wal, tmp_dest + '-wal')

                # 关键校验：复制期间源库若又变了，这份快照已不自洽，丢弃重来
                if _db_file_signature(db_path) != sig:
                    logger.info('复制快照期间源库发生变化，重试')
                    continue

                # 目标名带唯一戳，理论上不冲突；这里连 -shm 一起清掉——
                # 残留 -shm 会让 sqlite 跳过 WAL 恢复（详见函数 docstring）
                for stale in (dest, dest + '-wal', dest + '-shm'):
                    if os.path.exists(stale):
                        try:
                            os.remove(stale)
                        except OSError:
                            # -shm 正被其他只读连接占用时删不掉，
                            # 此时旧连接很快会释放，下轮重试即可
                            if stale.endswith('-shm'):
                                raise
                            pass
                os.replace(tmp_dest, dest)
                if os.path.exists(tmp_dest + '-wal'):
                    try:
                        os.replace(tmp_dest + '-wal', dest + '-wal')
                    except OSError:
                        # WAL 改名失败就必须丢弃这份快照，否则会读到过期数据
                        for f in (dest, dest + '-wal', tmp_dest, tmp_dest + '-wal'):
                            if os.path.exists(f):
                                try:
                                    os.remove(f)
                                except OSError:
                                    pass
                        raise
                break
            except OSError as e:
                last_err = e
                logger.warning(f'复制快照失败: {e}')
                break
        else:
            # 3 次都因"复制期间源库变化"而重试用尽，仍然失败
            last_err = last_err or RuntimeError('快照复制不稳定')
            logger.warning(f'快照复制多次不稳定，放弃: {last_err}')
            raise last_err if isinstance(last_err, OSError) else OSError(str(last_err))
    return dest


def _cleanup_old_snapshots(keep_path):
    """清理历史快照，只保留当前使用的那一份（避免临时目录无限膨胀）

    【2026-10】连 -wal / -shm 一起清。只删主库文件会留下孤立的伴生文件：
    - 残留 -shm 会让 sqlite 跳过 WAL 恢复（见 _refresh_live_snapshot 的说明）；
    - 残留 -wal 体积可达十几 MB，反复累积会撑爆临时目录。
    另需清理早期版本遗留的无版本号快照（zotero_snapshot.sqlite）。
    """
    snap_dir = os.path.dirname(keep_path)
    keep_names = {
        os.path.basename(keep_path),
        os.path.basename(keep_path) + '-wal',
        os.path.basename(keep_path) + '-shm',
    }
    try:
        for name in os.listdir(snap_dir):
            if not name.startswith('zotero_snapshot'):
                continue
            if name in keep_names:
                continue
            p = os.path.join(snap_dir, name)
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except OSError:
                # 可能仍被其他只读连接占用，交给下一轮刷新再清
                pass
    except OSError:
        pass


def get_db_connection():
    """
    获取数据库连接（读取"活快照"，保证读到最新数据）。

    返回值与原先一致：row_factory = sqlite3.Row 的只读连接。
    调用方仍需自行conn.close()。
    """
    try:
        db_path = get_db_path()
        if not db_path or not os.path.exists(db_path):
            raise sqlite3.Error(f"数据库文件不存在: {db_path}")

        with _snapshot_lock:
            sig = _db_file_signature(db_path)
            if _snapshot_state.get('sig') != sig or not os.path.exists(_snapshot_state['path']):
                try:
                    _snapshot_state['path'] = _refresh_live_snapshot(db_path)
                    _snapshot_state['sig'] = sig
                    logger.info('已刷新 Zotero 数据库活快照（含 WAL）')
                    _cleanup_old_snapshots(_snapshot_state['path'])
                except Exception as snap_err:
                    # 拷贝失败（如 Zotero 占用导致文件被锁）→ 退回过期快照，
                    # 保证功能降级可用而不是整体报错；后续还有 API 复核兜底
                    logger.warning(f'活快照刷新失败，退回 immutable 快照: {snap_err}')
                    _snapshot_state['sig'] = None
                    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
                    conn.row_factory = sqlite3.Row
                    return conn

            conn = sqlite3.connect(
                f"file:{_snapshot_state['path']}?mode=ro", uri=True, timeout=5
            )
            conn.row_factory = sqlite3.Row
            return conn
    except sqlite3.Error as e:
        logger.error(f"数据库连接错误: {e}")
        raise

def init_database():
    """初始化数据库路径"""
    try:
        logger.info("开始初始化数据库...")
        config = load_config()
        current_path = config.get('db_path', '')
        
        # 检查配置文件中是否有有效路径
        if current_path and os.path.exists(current_path):
            logger.info(f"配置文件中存在有效路径: {current_path}")
            # 显示倒计时对话框，允许用户修改
            selected_path = select_database_path(use_default=True)
        else:
            logger.info("配置文件中无有效路径，需要用户选择")
            # 强制用户选择路径
            selected_path = select_database_path(use_default=False)
        
        if not selected_path or not os.path.exists(selected_path):
            logger.error("未选择有效的数据库文件")
            # 显示错误对话框
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "数据库配置错误", 
                f"数据库文件不存在或无效。\n\n"
                f"请检查配置文件：\n{os.path.join(get_exe_directory(), 'zotero_config.json')}\n\n"
                f"或重新运行程序选择正确的数据库文件。"
            )
            root.destroy()
            return False
            
        set_db_path(selected_path)
        logger.info(f"成功设置数据库路径: {selected_path}")
        return True
        
    except Exception as e:
        logger.exception("初始化数据库时出错")
        return False

DOI_PREFIX_RE = re.compile(
    r'^\s*(?:https?://)?(?:dx\.)?doi\.org/|^\s*doi\s*:\s*|^\s*info:doi/',
    re.IGNORECASE
)

def normalize_identifier(identifier: str, id_type: str) -> str:
    """标准化 DOI / ISBN / PMID

    【2026-10 加固】DOI 兼容更多前缀写法（doi.org、dx.doi.org、info:doi/DOI），
    ISBN 新增 10 位与 13 位互转，使同一本书的不同 ISBN 写法可互相命中。
    """
    if not identifier:
        return None

    ident = identifier.strip()
    if id_type == 'doi':
        # 反复剥离，直到不再变化（部分标识符形如 "doi: https://doi.org/10.xxxx/yyy"）
        for _ in range(3):
            new_ident = DOI_PREFIX_RE.sub('', ident).strip()
            if new_ident == ident:
                break
            ident = new_ident
        ident = ident.lower().rstrip('.,;)]}\'"')
    elif id_type == 'pmid':
        # PMID 清洗：只保留纯数字
        ident = re.sub(r'[^0-9]', '', ident)
        if not ident: return None
    elif id_type == 'isbn':
        # 移除所有非数字和 'X' 字符
        ident = re.sub(r'[^0-9X]', '', ident.upper())

        # 验证 ISBN 长度
        if len(ident) not in [10, 13]:
            return None

        # ISBN-10 验证
        # 【2026-10 修正】原公式用 (10-i)*(9 if X else int(x))，权重与 X 处理均不正确，
        # 会误判合法 ISBN。标准算法：s = 10*d1 + 9*d2 + ... + 2*d9 + 1*d10，s % 11 == 0，
        # 其中校验位 d10 为 'X' 时按 10 计入（权重 1，值 10）。
        if len(ident) == 10:
            try:
                total = 0
                for i, ch in enumerate(ident):
                    value = 10 if ch == 'X' else int(ch)
                    total += (10 - i) * value
                if total % 11 != 0:
                    return None
            except ValueError:
                return None

        # ISBN-13 验证
        elif len(ident) == 13:
            try:
                total = sum((1 if i % 2 == 0 else 3) * int(x)
                          for i, x in enumerate(ident[:-1]))
                check = (10 - (total % 10)) % 10
                if int(ident[-1]) != check:
                    return None
            except ValueError:
                return None

    if not ident:
        return None
    return ident


def isbn10_to_isbn13(isbn10: str) -> str:
    """ISBN-10 转 ISBN-13（978 前缀 + 重算校验位）"""
    if not isbn10 or len(isbn10) != 10:
        return None
    core = '978' + isbn10[:9]
    total = sum((1 if i % 2 == 0 else 3) * int(x) for i, x in enumerate(core))
    check = (10 - (total % 10)) % 10
    return core + str(check)


def isbn13_to_isbn10(isbn13: str):
    """ISBN-13 转 ISBN-10；不成立时返回 None（979 前缀无法转回）"""
    if not isbn13 or len(isbn13) != 13:
        return None
    # 仅 978 前缀可逆，979 开头无法转回 ISBN-10
    if not isbn13.startswith('978'):
        return None
    core = isbn13[3:]  # 9 位主体 + ISBN-13 校验位
    body = core[:9]
    try:
        # ISBN-10 校验位：9 位主体按权重 10..2 加权后 (11 - total%11) % 11
        total = sum((10 - i) * int(x) for i, x in enumerate(body))
    except ValueError:
        return None
    check = (11 - (total % 11)) % 11
    candidate = body + ('X' if check == 10 else str(check))
    # 回验：标准 ISBN-10 公式（权重 10..1，X 记 10）
    try:
        verify = 0
        for i, ch in enumerate(candidate):
            value = 10 if ch == 'X' else int(ch)
            verify += (10 - i) * value
        if verify % 11 != 0:
            return None
    except ValueError:
        return None
    return candidate

def strip_html_tags(text):
    """去除字符串中的HTML标签"""
    if not text:
        return ''
    return re.sub(r'<[^>]+>', '', text)

def get_metadata_from_doi(doi):
    """从DOI获取文章元数据（增强版）

    【2026-10 加固】加入重试与退避、Crossref polite pool（mailto），
    并区分 404（DOI 不存在）与 5xx/429（服务端临时故障，应重试）。
    """
    # polite pool：Crossref 建议在 UA 中提供联系方式，可获得更稳定的服务
    contact = load_config().get('crossref_mailto', '')
    ua = 'ZoteroPicker/1.0 (https://github.com; mailto:{0})'.format(contact) if contact \
        else 'ZoteroPicker/1.0'
    headers = {
        'Accept': 'application/json',
        'User-Agent': ua
    }
    url = f'https://api.crossref.org/works/{requests.utils.quote(doi, safe="")}'

    response = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            # 404 表示 DOI 确实不存在，重试无意义
            if response.status_code == 404:
                logger.warning(f"DOI 不存在: {doi} (404)")
                return None
            if response.ok:
                break
            # 5xx / 429 视为临时故障，重试
            if attempt < 2:
                wait = 1.5 * (attempt + 1)
                logger.warning(f"Crossref 返回 {response.status_code}，{wait}s 后重试 ({attempt+1}/2)")
                time.sleep(wait)
                continue
            logger.warning(f"DOI获取失败: {doi}, 状态码: {response.status_code}")
            return None
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                wait = 1.5 * (attempt + 1)
                logger.warning(f"Crossref 请求异常({e})，{wait}s 后重试 ({attempt+1}/2)")
                time.sleep(wait)
                continue
            logger.error(f"DOI获取失败(网络异常): {doi}, {e}")
            return None

    if response is None or not response.ok:
        return None

    try:
        data = response.json().get('message', {})
    except ValueError:
        logger.warning(f"Crossref 返回非 JSON 内容: {doi}")
        return None

    # 以下为元数据字段提取（整体包在 try 中，任何异常都降级为 None）
    try:
        # 提取作者信息
        authors = []
        for author in data.get('author', []):
            if 'given' in author and 'family' in author:
                authors.append({
                    'creatorType': 'author',
                    'firstName': author.get('given', ''),
                    'lastName': author.get('family', '')
                })
            elif 'name' in author:
                # 机构作者通常只有一个 name 字段，用单字段名（lastName）承载更准确，
                # 避免被错误拆成 first/last
                authors.append({
                    'creatorType': 'author',
                    'lastName': author['name']
                })

        # 安全提取 title 和期刊名
        title = data.get('title')
        title_str = title[0] if isinstance(title, list) and title else f'[Untitled DOI: {doi}]'

        journal = data.get('container-title')
        journal_str = journal[0] if isinstance(journal, list) and journal else ''

        # 提取发表日期（优先 print，其次 online）
        def get_year(d):
            try:
                return str(d.get('date-parts', [[None]])[0][0])
            except Exception:
                return ''

        pub_date = get_year(data.get('published-print')) or get_year(data.get('published-online'))

        # 去HTML标签的摘要
        abstract_raw = data.get('abstract', '')
        abstract_clean = strip_html_tags(html.unescape(abstract_raw))

        metadata = {
            'itemType': 'journalArticle',
            'title': title_str,
            'DOI': doi,
            'creators': authors,
            'date': pub_date,
            'publicationTitle': journal_str,
            'volume': str(data.get('volume', '')),
            'issue': str(data.get('issue', '')),
            'pages': str(data.get('page', '')),
            'language': data.get('language', 'en'),
            'ISSN': data.get('ISSN', [None])[0] if isinstance(data.get('ISSN'), list) else '',
            'url': data.get('URL', ''),
            'abstractNote': abstract_clean,
            'tags': [{'tag': tag} for tag in data.get('subject', []) if tag],
            'extra': f'DOI: {doi}'
        }

        logger.info(f"成功获取DOI元数据: {doi}")
        return metadata

    except Exception as e:
        logger.error(f"获取DOI元数据失败: {str(e)}")
        return None


def get_metadata_from_pmid(pmid):
    """从 NCBI PubMed API 获取元数据"""
    try:
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
        response = requests.get(url, timeout=10)
        if not response.ok:
            logger.warning(f"PMID获取失败: {pmid}, 状态码: {response.status_code}")
            return None

        data = response.json()
        result = data.get('result', {}).get(pmid, {})
        if not result or 'error' in result:
            return None

        # 提取作者
        authors = []
        for author in result.get('authors', []):
            name_parts = author.get('name', '').split(' ', 1)
            authors.append({
                'creatorType': 'author',
                'firstName': name_parts[1] if len(name_parts) > 1 else '',
                'lastName': name_parts[0]
            })

        metadata = {
            'itemType': 'journalArticle',
            'title': result.get('title', f'[PMID: {pmid}]'),
            'creators': authors,
            'date': result.get('pubdate', ''),
            'publicationTitle': result.get('fulljournalname', result.get('source', '')),
            'volume': result.get('volume', ''),
            'issue': result.get('issue', ''),
            'pages': result.get('pages', ''),
            'extra': f'PMID: {pmid}' # 关键：Zotero 靠这个识别 PMID
        }
        
        # 如果 PubMed 数据里带有 DOI，一并顺过来
        for aid in result.get('articleids', []):
            if aid.get('idtype') == 'doi':
                metadata['DOI'] = aid.get('value')
                
        logger.info(f"成功获取PMID元数据: {pmid}")
        return metadata

    except Exception as e:
        logger.error(f"获取PMID元数据失败: {str(e)}")
        return None
    

def get_metadata_from_isbn(isbn):
    """从ISBN获取书籍元数据（占位符函数）"""
    # 这里可以实现从各种API获取ISBN元数据的逻辑
    logger.warning(f"ISBN元数据获取功能待实现: {isbn}")
    return None

def get_item_collections(conn, item_ids):
    """
    取条目所在分类，用于生成"跳到子分类"的链接。

    Zotero 官方 select 协议支持（源码 ZoteroProtocolHandler.mjs / SelectExtension）：
        zotero://select/library/collections/{collectionKey}/items/{itemKey}
    会先 selectCollection() 再 selectItems()，比只跳到"我的文库"根节点更贴近
    用户实际的查找路径。

    一个条目可能属于多个分类（实测本库 117 条），这里选**层级最深**的那个：
    你的分类树有 5 层，多分类条目中 86 条最深到第 4 层，那才是真正存放它的地方。
    同深度时按 collectionKey 升序取第一个，保证结果稳定可复现。

    返回 {itemID: {'key','name','path','libraryID'}}
    """
    if not item_ids:
        return {}

    placeholders = ','.join('?' * len(item_ids))
    # collectionItems 表只有 itemID + collectionID，没有 collectionKey，
    # 因此先取 (itemID, collectionID)，再用 collections 表补 key / 名称 / 层级。
    rel_rows = conn.execute(
        f"SELECT itemID, collectionID FROM collectionItems "
        f"WHERE itemID IN ({placeholders})",
        tuple(item_ids)
    ).fetchall()
    if not rel_rows:
        return {}

    col_rows = conn.execute(
        "SELECT collectionID, key, collectionName, parentCollectionID, libraryID "
        "FROM collections"
    ).fetchall()
    col_by_id = {r['collectionID']: dict(r) for r in col_rows}
    if not col_by_id:
        return {}

    def depth_of(cid):
        n, seen = 0, set()
        while cid in col_by_id and cid not in seen and n < 50:
            seen.add(cid)
            pid = col_by_id[cid]['parentCollectionID']
            if pid is None:
                break
            cid = pid
            n += 1
        return n

    path_cache = {}

    def path_of(cid):
        if cid in path_cache:
            return path_cache[cid]
        parts, seen = [], set()
        cur = cid
        while cur in col_by_id and cur not in seen and len(parts) < 50:
            seen.add(cur)
            parts.append(col_by_id[cur]['collectionName'])
            cur = col_by_id[cur]['parentCollectionID']
        path_cache[cid] = ' / '.join(reversed(parts))
        return path_cache[cid]

    depth_cache = {cid: depth_of(cid) for cid in col_by_id}
    best = {}
    for row in rel_rows:
        cid = row['collectionID']
        col = col_by_id.get(cid)
        if not col:
            continue
        d = depth_cache.get(cid, 0)
        cur = best.get(row['itemID'])
        # 选更深层；同深度按 key 升序，保证稳定
        if cur is None or d > cur['_depth'] or (d == cur['_depth'] and col['key'] < cur['key']):
            best[row['itemID']] = {
                'key': col['key'],
                'name': col['collectionName'],
                'path': path_of(cid),
                'libraryID': col['libraryID'],
                '_depth': d
            }

    for v in best.values():
        v.pop('_depth', None)
    return best


@app.route('/check_identifier', methods=['GET'])
def check_identifier():
    try:
        id_type = request.args.get('type', '').lower()
        identifier = request.args.get('identifier', '')
        
        if not identifier or id_type not in ['doi', 'isbn', 'pmid']:
            return jsonify({
                "error": "无效的标识符类型或值",
                "exists": False
            }), 400

        normalized = normalize_identifier(identifier, id_type)
        if not normalized:
            return jsonify({
                "error": f"无效的{id_type.upper()}格式",
                "exists": False
            }), 400

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            fieldName = 'DOI' if id_type == 'doi' else 'ISBN'

            # 【2026-10 重构】统一查重引擎，修四类问题：
            #  1) 排除回收站条目（deletedItems）—— 回收站里的文献不应显示"已存在"
            #  2) DOI/PMID 同时检索 extra 字段 —— 实测有 55 条 DOI、11 条 PMID 只存在 extra
            #  3) ISBN 支持 10 位/13 位互转 —— 同一本书不同 ISBN 写法可互相命中
            #  4) PMID 右边界精确匹配 —— 原 LIKE '%PMID: 12345%' 会误匹配 'PMID: 123456'
            # NOT IN (SELECT itemID FROM deletedItems) 是排除回收站的关键条件
            BASE_SQL = """
                SELECT DISTINCT i.itemID, i.key AS itemKey, i.libraryID, v.value AS Identifier
                FROM items i
                JOIN itemData d ON i.itemID = d.itemID
                JOIN itemDataValues v ON d.valueID = v.valueID
                JOIN fields f ON d.fieldID = f.fieldID
                WHERE i.itemID NOT IN (SELECT itemID FROM deletedItems)
            """
            ORDER_BY = " ORDER BY i.libraryID ASC"

            if id_type == 'doi':
                # DOI 匹配需容忍库中存储的完整 URL 形式（如 https://doi.org/10.xxxx/...）
                # Zotero 新版翻译器存库的 DOI 常带 URL 前缀，严格相等会漏匹配导致重复导入
                cursor.execute(BASE_SQL + """
                    AND f.fieldName = 'DOI'
                    AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(v.value),
                          'https://doi.org/', ''), 'http://dx.doi.org/', ''), 'https://dx.doi.org/', ''),
                          'doi:', ''), 'info:doi/', '') = ?
                """ + ORDER_BY, (normalized.lower(),))
                doi_field_rows = cursor.fetchall()

                # 补充检索 extra 字段中的 DOI
                # 【实测数据形态】extra 里常见两种形态，需同时覆盖：
                #   ① "DOI: 10.xxx/yyy"（Zotero 老版本/手工录入）
                #   ② "_eprint: https://onlinelibrary.wiley.com/doi/pdf/10.1002/mp.17051"
                #      （DOI 嵌在 URL 路径中，不能要求 DOI 前面紧邻 "DOI:"）
                # 因此只要求 DOI 出现在 extra 文本中，再在 Python 侧做边界收敛，
                # 避免 SQL 直接 LIKE 带来的误命中（如 10.1002/mp.17 命中 mp.17051）。
                cursor.execute(BASE_SQL + """
                    AND f.fieldName = 'extra'
                    AND LOWER(v.value) LIKE '%' || ? || '%'
                """ + ORDER_BY, (normalized.lower(),))
                extra_rows = cursor.fetchall()

                # 合并去重（同一 itemID 只保留一条）
                # 注意：extra 字段可能包含整段摘要，直接回传会污染前端展示，
                # 因此 extra 来源的记录把 Identifier 收敛为纯 DOI。
                merged = {}
                for row in doi_field_rows:
                    merged[row['itemID']] = dict(row)
                for row in extra_rows:
                    rec = dict(row)
                    rec['Identifier'] = normalized
                    rec['MatchedField'] = 'extra'
                    merged.setdefault(row['itemID'], rec)
                results = list(merged.values())

            elif id_type == 'isbn':
                # ISBN 必须处理 Zotero 数据库自带的连字符、空格以及附加字符
                # REPLACE(REPLACE(UPPER(v.value), '-', ''), ' ', '') 相当于把数据库里的值临时洗干净
                # LIKE ? 允许匹配包含该 ISBN 的长字符串（如 "9781234567890 (电子书)"）
                # 2026-10：同时用互转后的另一种写法查询，避免 10 位/13 位互相漏匹配
                candidates = {normalized.upper()}
                if len(normalized) == 10:
                    alt = isbn10_to_isbn13(normalized)
                    if alt:
                        candidates.add(alt)
                elif len(normalized) == 13:
                    alt = isbn13_to_isbn10(normalized)
                    if alt:
                        candidates.add(alt.upper())

                isbn_results = []
                for cand in candidates:
                    cursor.execute(BASE_SQL + """
                        AND f.fieldName = ?
                        AND REPLACE(REPLACE(UPPER(v.value), '-', ''), ' ', '') LIKE ?
                    """ + ORDER_BY, (fieldName, f"%{cand}%"))
                    isbn_results.extend(cursor.fetchall())

                merged = {}
                for row in isbn_results:
                    merged[row['itemID']] = dict(row)
                results = list(merged.values())

            else:  # pmid
                # 【实测数据形态】Zotero 把 PMID 存在 extra 字段。实测本库 11 条 PMID
                # 全部为 URL 形式："PMID: http://www.ncbi.nlm.nih.gov/pubmed/34452573"，
                # 因此必须包含 pubmed URL 模式，否则一条都匹配不到（实测仅 URL 模式命中）。
                # 同时兼容简写形式："PMID: 34452573"、"PMID:34452573"、"PMID 34452573"。
                # 右边界统一用 [^0-9]*，避免 34452573 被 344525731 误匹配。
                cursor.execute(BASE_SQL + """
                    AND f.fieldName = 'extra'
                    AND (
                        UPPER(v.value) GLOB '*PMID: HTTP://WWW.NCBI.NLM.NIH.GOV/PUBMED/' || ? || '[^0-9]*'
                     OR UPPER(v.value) GLOB '*PUBMED/' || ? || '[^0-9]*'
                     OR UPPER(v.value) GLOB '*PMID:' || ? || '[^0-9]*'
                     OR UPPER(v.value) GLOB '*PMID ' || ? || '[^0-9]*'
                    )
                """ + ORDER_BY, (normalized, normalized, normalized, normalized))
                # extra 全文可能极长（含摘要、期刊分区等），回传时收敛为纯 PMID，
                # 避免前端展示与日志输出被大段文本污染。
                results = []
                for row in cursor.fetchall():
                    rec = dict(row)
                    rec['Identifier'] = f"PMID: {normalized}"
                    results.append(rec)

            results = list(results) if results else []

            # 【2026-10 权威复核】sqlite 快照与 Zotero 内存状态之间存在时间差：
            # 用户可能在查询之后、点击跳转之前删除了条目。此时若仍返回 exists=true，
            # 页面会显示"已存在"但 zotero://select/items/ 跳转提示找不到条目。
            # 这里用 Zotero 在线 API 二次确认，剔除已删除/已进回收站的条目。
            if results:
                key_lib_map = {
                    r['itemKey']: r.get('libraryID') for r in results
                }
                alive = filter_alive_item_keys(
                    [r['itemKey'] for r in results], key_lib_map, conn
                )
                if alive is None:
                    # 无法复核（Zotero 未运行/请求失败）→ 保留原结果，降级可用
                    logger.info("itemKey 复核不可用，保留 sqlite 查询结果")
                else:
                    dropped = [r for r in results if r['itemKey'] not in alive]
                    if dropped:
                        logger.info(
                            "API 复核剔除了 %d 个已失效条目: %s",
                            len(dropped), [r['itemKey'] for r in dropped]
                        )
                    results = [r for r in results if r['itemKey'] in alive]

            items_list = [dict(row) for row in results] if results else []

            # 【2026-10】附上条目所在分类，供前端生成"跳到子分类"的链接。
            # Zotero 官方协议支持 zotero://select/library/collections/{colKey}/items/{itemKey}，
            # 会先选中分类再选中条目，比只跳到文库根节点更贴近实际查找路径。
            if items_list:
                col_map = get_item_collections(
                    conn, [it['itemID'] for it in items_list]
                )
                # 取各library 的类型（user / group / feed），
                # 前端据此选择 zotero:// 的 library 还是 groups 路由。
                # 群组库还要带出真实 groupID：官方协议走 groups/{groupID}/ 路由，
                # 而 zotero:// 用的是 groups 表的 groupID（本库 6212837），
                # 不是 libraries.libraryID（本库 8），传错会定位不到库。
                lib_type = {}
                group_id_map = {}
                if items_list:
                    lib_ids = tuple({it['libraryID'] for it in items_list})
                    ph = ','.join('?' * len(lib_ids))
                    for r in conn.execute(
                        f"SELECT libraryID, type FROM libraries WHERE libraryID IN ({ph})",
                        lib_ids
                    ).fetchall():
                        lib_type[r['libraryID']] = r['type']
                    for r in conn.execute(
                        f"SELECT libraryID, groupID FROM groups WHERE libraryID IN ({ph})",
                        lib_ids
                    ).fetchall():
                        group_id_map[r['libraryID']] = r['groupID']
                for it in items_list:
                    col = col_map.get(it.get('itemID'))
                    it['collection'] = col if col else None
                    it['libraryType'] = lib_type.get(it.get('libraryID'), 'user')
                    it['groupID'] = group_id_map.get(it.get('libraryID'))

            if items_list:
                logger.info(f"为该标识符找到了 {len(items_list)} 个匹配项 (按 libraryID 排序):")
                for idx, item in enumerate(items_list):
                    logger.info(f"  - 匹配项 [{idx}]: libraryID = {item.get('libraryID')}, itemKey = {item.get('itemKey')}, itemID = {item.get('itemID')}")
            else:
                logger.info("未在数据库中找到该标识符。")

            return jsonify({
                "exists": bool(results),
                "items": items_list,
                "verified": True
            })
        finally:
            conn.close()

    except Exception as e:
        logger.exception("检查标识符时出错")
        return jsonify({
            "error": str(e),
            "exists": False
        }), 500

def _api_normalize_doi(value):
    """把 API 返回的 DOI 值规范化为裸 DOI（小写、剥前缀）"""
    if not value:
        return None
    v = str(value).strip().lower()
    for _ in range(3):
        nv = DOI_PREFIX_RE.sub('', v).strip()
        if nv == v:
            break
        v = nv
    return v.rstrip('.,;)]}\'"') or None


def _api_item_matches_id(item_data, id_type, normalized):
    """在单个 API 返回的条目中做精确标识符比对（避免全文检索的假阳性）"""
    if id_type == 'doi':
        want = normalized.lower()
        if _api_normalize_doi(item_data.get('DOI')) == want:
            return True
        extra = item_data.get('extra') or ''
        return want in extra.lower()
    if id_type == 'pmid':
        extra = (item_data.get('extra') or '')
        return re.search(rf'PMID\s*:?\s*/?{re.escape(normalized)}\b', extra, re.IGNORECASE) is not None
    if id_type == 'isbn':
        extra = (item_data.get('extra') or '')
        for field in ('ISBN', extra):
            digits = re.sub(r'[^0-9X]', '', str(field).upper())
            if normalized.upper() in digits:
                return True
            alt = isbn10_to_isbn13(normalized) if len(normalized) == 10 else isbn13_to_isbn10(normalized)
            if alt and alt.upper() in digits:
                return True
        return False
    return False


def _confirm_import_via_api(zotero_url, headers, id_type, normalized, max_items=25):
    """导入成功后通过 Zotero HTTP API 实时校验条目是否落库，并返回真实 itemKey。

    背景：sqlite 以 immutable 只读快照方式打开，会忽略 Zotero 的 -wal 文件，
    因此刚写入的条目在快照里不可见，前端轮询必然查不到。
    这里改用 API 拉取"最近添加"的条目（实测 0.78s，全文检索需 3.3s），
    再在 Python 侧做精确标识符比对，既快又不会误判。
    """
    api_base = zotero_url.replace('/connector', '')
    try:
        # 【2026-10 修复】原本只查 users/0（个人文库）。若 Zotero 当前选中的
        # 目标库是群组库，条目会保存到 groups/{groupID} 下，users/0 里查不到，
        # 导致前端拿不到 itemKey、无法显示"已存在+跳转"链接。
        # 现在把个人库与群组库都纳入候选，逐库查找后再排除自身。
        # feed 库不纳入：Zotero 本地 API 无 feed 端点（实测 404）。
        prefixes = ['/api/users/0/items']
        conn_try = None
        try:
            conn_try = get_db_connection()
            rows = conn_try.execute(
                "SELECT l.libraryID, l.type, g.groupID "
                "FROM libraries l "
                "LEFT JOIN groups g ON g.libraryID = l.libraryID"
            ).fetchall()
            for r in rows:
                if r['type'] == 'group' and r['groupID']:
                    prefixes.append(f"/api/groups/{r['groupID']}/items")
                elif r['type'] == 'feed':
                    # 本地 API 无 feed 端点（实测 404），不加入候选
                    continue
        except Exception as e:
            logger.warning(f"枚举库列表失败，仅查个人文库: {e}")

        self_key = None
        try:
            if conn_try is not None:
                row = conn_try.execute(
                    "SELECT key FROM items ORDER BY itemID DESC LIMIT 1"
                ).fetchone()
                if row:
                    self_key = row['key']
        except Exception:
            pass

        try:
            for prefix in prefixes:
                resp = requests.get(
                    f"{api_base}{prefix}",
                    params={
                        'limit': max_items,
                        'sort': 'dateAdded',
                        'direction': 'desc',
                        'itemType': '-attachment || note || annotation',
                    },
                    headers=headers,
                    timeout=10
                )
                if not resp.ok:
                    logger.warning(f"导入后校验失败（{prefix} HTTP {resp.status_code}）")
                    continue

                items = resp.json()
                if not isinstance(items, list):
                    continue

                for it in items:
                    # 跳过 sqlite 快照里已有的老条目，避免把旧条目误当成"本次导入"
                    if self_key and it.get('key') == self_key:
                        continue
                    data = it.get('data', {})
                    if _api_item_matches_id(data, id_type, normalized):
                        library = data.get('library', {})
                        # library.id 对我的文库为 0/1 视版本而定，zotero:// 协议需要数字 libraryID
                        return [{
                            "itemID": None,
                            "itemKey": it.get('key'),
                            "libraryID": library.get('id', 1),
                            "Identifier": data.get(id_type.upper()) or normalized,
                            "title": data.get('title', '')
                        }]
        finally:
            if conn_try is not None:
                try:
                    conn_try.close()
                except Exception:
                    pass

        logger.info(f"导入后 API 校验：未在最近 {max_items} 条中匹配到 {id_type.upper()}={normalized}（可能仍在写入）")
        return None
    except Exception as e:
        logger.warning(f"导入后校验异常（不影响导入成功）: {e}")
        return None


@app.route('/import_item', methods=['POST'])
def import_item():
    try:
        data = request.json
        logger.info(f"收到导入请求: {json.dumps(data, ensure_ascii=False)}")
        
        id_type = data.get('type', '')
        identifier = data.get('identifier', '')

        if id_type not in ['doi', 'isbn', 'pmid'] or not identifier:
            return jsonify({"success": False, "message": "Invalid type or identifier"}), 400

        normalized = normalize_identifier(identifier, id_type)
        if not normalized:
            return jsonify({"success": False, "message": f"Invalid {id_type} identifier"}), 400

        # 获取元数据
        if id_type == 'doi':
            metadata = get_metadata_from_doi(normalized)
        elif id_type == 'pmid':
            metadata = get_metadata_from_pmid(normalized)
        elif id_type == 'isbn':  # ISBN
            metadata = get_metadata_from_isbn(normalized)

        if metadata:
            items = [metadata]
        else:
            items = [{
                "itemType": "journalArticle" if id_type == "doi" else "book",
                "title": f"[Importing] {normalized}",
                id_type.upper(): normalized,
                "extra": f"{id_type.upper()}: {normalized}"
            }]

        # 【Zotero 7+ 兼容性修复（2026-10）】
        # Zotero 7 起，本地 HTTP 服务器（server.js）增加了防 DNS rebinding 保护：
        # User-Agent 以 "Mozilla/" 开头、或带有 Origin 头的请求会被判定为
        # "浏览器请求"并直接断连（不返回任何响应），除非请求携带
        # X-Zotero-Connector-API-Version 头（或 Zotero-Allowed-Request 头）。
        # 另外 saveItems 端点要求连接器 API 版本 >= 3，低于 3 会返回
        # 400 CONNECTOR_VERSION_OUTDATED。Zotero 6 无此限制，
        # 这就是 Zotero 升级到 7/10 后通讯失败的根本原因。
        zotero_headers = get_zotero_headers()

        # 尝试不同的 Zotero 基础 URL
        # 【性能】127.0.0.1 优先：避免 localhost 解析到 IPv6 ::1 后的超时回退
        base_urls = ['http://127.0.0.1:23119', 'http://localhost:23119']

        for zotero_url in base_urls:
            try:
                # 首先进行 ping 测试
                ping_response = requests.get(
                    f"{zotero_url}/connector/ping",
                    timeout=5,
                    headers=zotero_headers
                )

                if not ping_response.ok:
                    logger.warning(f"Zotero ping 未通过 ({zotero_url}): HTTP {ping_response.status_code}")
                    continue

                logger.info(f"成功连接到 Zotero ({zotero_url})")

                # 发送导入请求
                headers = dict(zotero_headers)

                save_data = {
                    "items": items,
                    "url": f"https://doi.org/{normalized}" if id_type == "doi" else "",
                    "sessionID": f"extension_import_{int(time.time()*1000)}"
                }
                # 【2026-10 优化】移除硬编码的 "target": "L1"
                # 原代码强制写入"我的文库"根目录，会忽略用户在 Zotero 中当前选中的
                # 库或分类（getSaveTarget 会退回 lastViewedFolder，即用户上次所在位置）。
                # 不传 target 时由 Zotero 自行决定保存位置，对多库用户更符合预期。

                response = requests.post(
                    f"{zotero_url}/connector/saveItems",
                    json=save_data,
                    headers=headers,
                    timeout=10
                )

                if response.ok or response.status_code == 201:
                    # 【2026-10 新增】导入后立即用 Zotero HTTP API 精确校验。
                    # 原因：后端查重走 sqlite immutable 快照，读不到 Zotero 刚写入 WAL
                    # 的新数据，导致前端轮询查不到、误以为导入失败而重复点击。
                    # API 能读到实时数据，并回传真实的 itemKey 供前端跳转。
                    confirmed = _confirm_import_via_api(
                        zotero_url, zotero_headers, id_type, normalized
                    )
                    result = {
                        "success": True,
                        "message": "Item successfully imported"
                    }
                    if confirmed:
                        result["items"] = confirmed
                        result["verified"] = True
                    return jsonify(result)

                if response.status_code == 409:
                    logger.warning(f"Zotero 会话冲突 ({zotero_url})，1秒后重试")
                    time.sleep(1)
                    continue

                # 记录异常响应详情，便于排查（如 400 CONNECTOR_VERSION_OUTDATED 等）
                logger.warning(
                    f"Zotero saveItems 返回异常 ({zotero_url}): "
                    f"HTTP {response.status_code}, body: {response.text[:500]}"
                )
                
            except requests.exceptions.RequestException as e:
                logger.error(f"连接Zotero失败 ({zotero_url}): {str(e)}")
                continue
        
        return jsonify({
            "success": False,
            "message": "无法连接到Zotero，请确保Zotero正在运行"
        }), 500

    except Exception as e:
        logger.exception("导入条目时出错")
        return jsonify({
            "success": False, 
            "message": f"导入过程发生错误: {str(e)}"
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """健康检查：供浏览器扩展探测后端与 Zotero 的连通性

    【2026-10 新增】此前 content.js 用 ?type=doi&identifier=test 探测服务，
    该请求会走到 DOI 校验并返回 400，语义不清且会做无意义的库查询。
    """
    db_ok = False
    db_error = None
    try:
        conn = get_db_connection()
        try:
            conn.execute('SELECT 1').fetchone()
            db_ok = True
        finally:
            conn.close()
    except Exception as e:
        db_error = str(e)

    zotero_ok = False
    zotero_version = None
    zotero_error = None
    for base in ('http://127.0.0.1:23119', 'http://localhost:23119'):
        try:
            r = requests.get(
                f"{base}/connector/ping",
                timeout=3,
                headers={
                    # 非浏览器 UA，避免 Zotero 7+ 的浏览器请求防护断连
                    'User-Agent': 'ZoteroPickerBackend/1.0',
                    'X-Zotero-Connector-API-Version': '3'
                }
            )
            if r.ok:
                zotero_ok = True
                zotero_version = r.headers.get('X-Zotero-Version')
                break
        except Exception as e:
            zotero_error = str(e)

    status = 200 if db_ok else 503
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "database": {"ok": db_ok, "error": db_error},
        "zotero": {"ok": zotero_ok, "version": zotero_version, "error": zotero_error}
    }), status


@app.route('/config', methods=['GET', 'POST'])
def config_endpoint():
    """配置管理接口"""
    if request.method == 'GET':
        config = load_config()
        return jsonify(config)
    
    elif request.method == 'POST':
        try:
            new_config = request.json
            save_config(new_config)
            # 重新加载数据库路径
            set_db_path(new_config.get('db_path', ''))
            return jsonify({"success": True, "message": "配置已更新"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500

# @app.errorhandler(Exception)
# def handle_exception(e):
#     """全局异常处理"""
#     logger.exception("服务器错误")
#     return jsonify({"error": str(e)}), 500
# 【修改后的代码】
@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理"""
    # 改用 logger.error，并且只打印具体的错误原因，不打印底层的系统调用栈
    logger.error(f"服务器错误: {str(e)}") 
    return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    try:
        logger.info("程序启动...")
        logger.info(f"程序运行目录: {get_exe_directory()}")
        
        if not init_database():
            logger.error("数据库初始化失败，程序退出")
            sys.exit(1)
            
        logger.info("启动Zotero服务器...")
        app.run(host='127.0.0.1', port=5000, debug=False)
    except Exception as e:
        logger.exception("程序启动失败")
        # 显示错误对话框
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("程序启动失败", f"发生错误：{str(e)}")
            root.destroy()
        except:
            pass
        sys.exit(1)
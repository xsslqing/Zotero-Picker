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
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sys
import html

app = Flask(__name__)
CORS(app)

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

def get_db_connection():
    """获取数据库连接"""
    try:
        db_path = get_db_path()
        if not db_path or not os.path.exists(db_path):
            raise sqlite3.Error(f"数据库文件不存在: {db_path}")
        
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
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

def normalize_identifier(identifier: str, id_type: str) -> str:
    """标准化 DOI 或 ISBN"""
    if not identifier:
        return None
        
    ident = identifier.strip()
    if id_type == 'doi':
        ident = ident.lower().replace("doi:", "").replace("https://doi.org/", "")
        ident = ident.strip().rstrip('.')
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
        if len(ident) == 10:
            try:
                total = sum((10 - i) * (9 if x == 'X' else int(x)) 
                          for i, x in enumerate(ident))
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

def strip_html_tags(text):
    """去除字符串中的HTML标签"""
    if not text:
        return ''
    return re.sub(r'<[^>]+>', '', text)

def get_metadata_from_doi(doi):
    """从DOI获取文章元数据（增强版）"""
    try:
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(
            f'https://api.crossref.org/works/{doi}',
            headers=headers,
            timeout=10
        )
        
        if not response.ok:
            logger.warning(f"DOI获取失败: {doi}, 状态码: {response.status_code}")
            return None

        data = response.json().get('message', {})
        
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
                name_parts = author['name'].split(' ', 1)
                authors.append({
                    'creatorType': 'author',
                    'firstName': name_parts[0] if len(name_parts) > 1 else '',
                    'lastName': name_parts[1] if len(name_parts) > 1 else name_parts[0]
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

@app.route('/check_identifier', methods=['GET'])
def check_identifier():
    try:
        id_type = request.args.get('type', '').lower()
        identifier = request.args.get('identifier', '')
        
        if not identifier or id_type not in ['doi', 'isbn']:
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
            
            # 【核心修改：将 DOI 和 ISBN 的查询策略分开】
            if id_type == 'doi':
                # DOI 比较标准，严格匹配即可
                cursor.execute("""
                    SELECT i.itemID, i.key AS itemKey, i.libraryID, v.value AS Identifier
                    FROM items i
                    JOIN itemData d ON i.itemID = d.itemID
                    JOIN itemDataValues v ON d.valueID = v.valueID
                    JOIN fields f ON d.fieldID = f.fieldID
                    WHERE f.fieldName = ? AND LOWER(v.value) = ?
                    ORDER BY i.libraryID ASC
                """, (fieldName, normalized.lower()))
            elif id_type == 'isbn':
                # ISBN 必须处理 Zotero 数据库自带的连字符、空格以及附加字符
                # REPLACE(REPLACE(UPPER(v.value), '-', ''), ' ', '') 相当于把数据库里的值临时洗干净
                # LIKE ? 允许匹配包含该 ISBN 的长字符串（如 "9781234567890 (电子书)"）
                cursor.execute("""
                    SELECT i.itemID, i.key AS itemKey, i.libraryID, v.value AS Identifier
                    FROM items i
                    JOIN itemData d ON i.itemID = d.itemID
                    JOIN itemDataValues v ON d.valueID = v.valueID
                    JOIN fields f ON d.fieldID = f.fieldID
                    WHERE f.fieldName = ? 
                    AND REPLACE(REPLACE(UPPER(v.value), '-', ''), ' ', '') LIKE ?
                    ORDER BY i.libraryID ASC
                """, (fieldName, f"%{normalized.upper()}%"))
            elif id_type == 'pmid':
                # Zotero 通常把 PMID 存在 extra 字段中
                cursor.execute("""
                    SELECT i.itemID, i.key AS itemKey, i.libraryID, v.value AS Identifier
                    FROM items i
                    JOIN itemData d ON i.itemID = d.itemID
                    JOIN itemDataValues v ON d.valueID = v.valueID
                    JOIN fields f ON d.fieldID = f.fieldID
                    WHERE f.fieldName = 'extra' 
                    AND UPPER(v.value) LIKE ?
                    ORDER BY i.libraryID ASC
                """, (f"%PMID: {normalized}%",))
            
            results = cursor.fetchall()
            
            items_list = [dict(row) for row in results] if results else []
            
            if items_list:
                logger.info(f"为该标识符找到了 {len(items_list)} 个匹配项 (按 libraryID 排序):")
                for idx, item in enumerate(items_list):
                    logger.info(f"  - 匹配项 [{idx}]: libraryID = {item.get('libraryID')}, itemKey = {item.get('itemKey')}, itemID = {item.get('itemID')}")
            else:
                logger.info("未在数据库中找到该标识符。")

            return jsonify({
                "exists": bool(results),
                "items": items_list
            })
        finally:
            conn.close()

    except Exception as e:
        logger.exception("检查标识符时出错")
        return jsonify({
            "error": str(e),
            "exists": False
        }), 500

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

        # 尝试不同的 Zotero 基础 URL
        base_urls = ['http://localhost:23119', 'http://127.0.0.1:23119']
        
        for zotero_url in base_urls:
            try:
                # 首先进行 ping 测试
                ping_response = requests.get(
                    f"{zotero_url}/connector/ping",
                    timeout=5,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                
                if not ping_response.ok:
                    continue

                logger.info(f"成功连接到 Zotero ({zotero_url})")

                # 发送导入请求
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0',
                    'Zotero-Connector-API-Version': '2'
                }

                save_data = {
                    "items": items,
                    "url": f"https://doi.org/{normalized}" if id_type == "doi" else "",
                    "sessionID": f"extension_import_{int(time.time()*1000)}",
                    "target": "L1"
                }

                response = requests.post(
                    f"{zotero_url}/connector/saveItems",
                    json=save_data,
                    headers=headers,
                    timeout=10
                )

                if response.ok or response.status_code == 201:
                    return jsonify({
                        "success": True,
                        "message": "Item successfully imported"
                    })

                if response.status_code == 409:
                    time.sleep(1)
                    continue
                
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

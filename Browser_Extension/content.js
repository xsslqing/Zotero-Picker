class ZoteroPicker {
  constructor() {
    // 标识符检测模式
    this.identifierPatterns = this.initializePatterns();
    
    this.processedIdentifiers = new Set();
    this.observeTimeout = null;
    this.serviceAvailable = false;
    this.debounceDelay = 100;
    this.checkCache = new Map();
    // 【2026-10 下调】原为 5 分钟，过长导致：用户在 Zotero 里删除文献后，
    // 网页仍显示旧的"已存在"标记（正是用户报告的现象）。改为 30 秒——
    // 足够消除同一页面的重复请求，又能让库中改动较快反映到页面。
    this.cacheExpiration = 30 * 1000;
    
    // 样式配置
    this.styles = {
      marker: {
        new: { text: '✕', color: '#d52b1e', title: 'Not in Zotero - Click to add' },
        exists: { text: '✓', color: '#5dd95d', title: 'Exists in Zotero' },
        offline: { text: '!', color: '#999', title: 'Zotero service unavailable' }
      }
    };

    // 【2026-10 新增】强制刷新：清空查重缓存并重扫页面。
    // 触发方式：在页面上按 Alt+Shift+R，或从扩展入口调用。
    // 用途：用户刚在 Zotero 里增删条目后，无需等待缓存过期即可立即刷新状态。
    document.addEventListener('keydown', (e) => {
      if (e.altKey && e.shiftKey && (e.code === 'KeyR' || e.key === 'R' || e.key === 'r')) {
        e.preventDefault();
        this.forceRefresh();
      }
    });

    console.log('ZoteroPicker初始化 - 仅支持 DOI/ISBN/PMID');
  }

  /**
   * 强制刷新所有标识符状态（忽略缓存）。
   * 先清空 checkCache 让下次查询走网络，再让已渲染的标记重新查一次。
   */
  async forceRefresh() {
    this.checkCache.clear();
    console.log('ZoteroPicker: 已清空查重缓存，强制重新查询');

    const markers = document.querySelectorAll('.zotero-picker-wrapper');
    let n = 0;
    for (const wrapper of markers) {
      const dataset = wrapper.dataset;
      if (!dataset || !dataset.zpType || !dataset.zpIdentifier) continue;
      try {
        const fresh = await this.checkZotero(dataset.zpType, dataset.zpIdentifier);
        const marker = wrapper.querySelector('.zotero-marker');
        if (marker) {
          this.updateMarkerStyle(marker, fresh);
          n++;
        }
      } catch (err) {
        console.warn('强制刷新失败:', err);
      }
    }
    console.log(`ZoteroPicker: 已刷新 ${n} 个标识符`);
  }

  initializePatterns() {
    return {
      // DOI检测模式
      // 【2026-10 修正】原正则的尾部终止符不含逗号/右括号/右花括号，
      // 导致 "10.1016/xxx," 这类文本抓出的 DOI 带尾部标点（查重必然失败）。
      // 现改为：右侧用后顾断言要求结尾是真正的 DOI 结束位置（空白/结束/引号/常见标点），
      // 尾部标点再由 normalizeDOI() 统一清洗。
      //
      // 字符类说明：
      //  - 前导字符保留 '/'：否则 https://doi.org/10.xxxx/yyy 这类 URL 形式
      //    （文献页最常见形态）会完全漏检；保留 '"' 与 "'" 以覆盖引号包裹的写法。
      //  - 右侧排除集保留 ()[] ，但**保留 {}**：部分 DOI 含花括号（如 SICI 编码），
      //    排除 {} 会把 DOI 从右花括号处截断。
      //  - 右侧排除集不含 < >：SICI 型 DOI 含 <...> 片段
      //    (10.1002/(SICI)1097-0258(19980815)17:15<1661::AID-SIM968>3.0.CO;2-2)，
      //    误排除会导致漏检。
      doi: [
        {
          regex: /(\s|\>|:|^|;|,|\/|\(|\[|"|')(10\.\d{4,9}\/[^\s"'\[\]()]+)(\)|\]|\s|\.\s|&nbsp;|[.,;:!?'"]|$)/g,
          captureGroup: 2
        }
      ],
      
      // ISBN检测模式
      isbn: [
        // ISBN-13模式
        {
          regex: /(\s|\>|:|^|;|,)((978\-|979\-)(\d|\-){11,13})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN13'
        },
        {
          regex: /(\s|\>|:|^|;|,)((978\s|979\s)(\d|\s){11,13})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN13'
        },
        {
          regex: /(\s|\>|:|^|;|,)((978|979)(\-){0,1}(\d|\s){10})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN13'
        },
        // ISBN-10模式
        {
          regex: /(\s|\>|:|^|;|,)((\d|x|X){10})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN10'
        },
        {
          regex: /(\s|\>|:|^|;|,)((\d|\-|x|X){13})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN10'
        },
        {
          regex: /(\s|\>|:|^|;|,)((\d|\-|x|X){12})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN10'
        },
        {
          regex: /(\s|\>|:|^|;|,)((\d|\-|x|X){11})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN10'
        },
        {
          regex: /(\s|\>|:|^|;|,)((\d|\s|x|X){13})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN10'
        },
        {
          regex: /(\s|\>|:|^|;|,)((\d|\s|x|X){12})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN10'
        },
        {
          regex: /(\s|\>|:|^|;|,)((\d|\s|x|X){11})($|\D)/g,
          captureGroup: 2,
          type: 'ISBN10'
        }
      ]
    };
  }

  // 标识符检测逻辑
  getIdentifier(text, startIndex, type) {
    try {
      if (!text || text === ' ') return null;

      // 如果没有指定类型，尝试所有类型
      if (!type) {
        return this.getAnyIdentifier(text, startIndex);
      }

      const patterns = this.identifierPatterns[type] || [];
      let bestMatch = null;

      patterns.forEach((pattern) => {
        const regex = new RegExp(pattern.regex.source, pattern.regex.flags);
        regex.lastIndex = startIndex;
        const match = regex.exec(text);
        
        if (match) {
          const identifier = match[pattern.captureGroup];
          let isValid = false;

          // 根据类型验证标识符
          switch (type) {
            case 'isbn':
              if (pattern.type === 'ISBN13') {
                isValid = this.isISBN13(identifier);
              } else {
                isValid = this.isISBN10(identifier);
              }
              break;
            case 'doi':
              // 【2026-10】原判断为 identifier.indexOf('10.') !== -1，过于宽松；
              // 改为严格形态校验，避免抓到 URL 路径片段等误匹配
              isValid = this.isValidDOI(identifier);
              break;
            default:
              isValid = true;
          }

          if (isValid && (!bestMatch || bestMatch.index > match.index)) {
            bestMatch = match;
            bestMatch.identifier = identifier;
            bestMatch.identifierType = type;
          }
        }
      });

      return bestMatch;
    } catch (e) {
      console.warn('标识符检测出错:', e);
      return null;
    }
  }

  // 全类型标识符检测 (仅 DOI/ISBN)
  getAnyIdentifier(text, startIndex) {
    try {
      // ISBN检测模式数组 
      const patterns = [];
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((978\-|979\-)(\d|\-){11,13})($|\D)/g, type: 'ISBN13' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((978\s|979\s)(\d|\s){11,13})($|\D)/g, type: 'ISBN13' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((978|979)(\-){0,1}(\d|\s){10})($|\D)/g, type: 'ISBN13' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((\d|x|X){10})($|\D)/g, type: 'ISBN10' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((\d|\-|\-|x|X){13})($|\D)/g, type: 'ISBN10' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((\d|\-|\-|x|X){12})($|\D)/g, type: 'ISBN10' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((\d|\-|\-|x|X){11})($|\D)/g, type: 'ISBN10' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((\d|\s|x|X){13})($|\D)/g, type: 'ISBN10' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((\d|\s|x|X){12})($|\D)/g, type: 'ISBN10' });
      patterns.push({ rgx: /(\s|\>|:|^|;|,)((\d|\s|x|X){11})($|\D)/g, type: 'ISBN10' });

      // 检测ISBN
      let isbnMatch = null;
      patterns.forEach((pattern) => {
        const rgx = pattern.rgx;
        rgx.lastIndex = startIndex;
        const match = rgx.exec(text);
        if (match != null) {
          if (pattern.type === 'ISBN13') {
            if (this.isISBN13(match[2])) {
              if (isbnMatch == null || isbnMatch.index > match.index) {
                isbnMatch = match;
                isbnMatch.identifierType = 'isbn';
                isbnMatch.identifier = match[2];
              }
            }
          } else {
            if (this.isISBN10(match[2])) {
              if (isbnMatch == null || isbnMatch.index > match.index) {
                isbnMatch = match;
                isbnMatch.identifierType = 'isbn';
                isbnMatch.identifier = match[2];
              }
            }
          }
        }
      });
      
      if (isbnMatch != null) {
        return isbnMatch;
      }

      // DOI检测（必须与 initializePatterns 中的定义保持一致）
      const doiReg = /(\s|\>|:|^|;|,|\/|\(|\[|"|')(10\.\d{4,9}\/[^\s"'\[\]()]+)(\)|\]|\s|\.\s|&nbsp;|[.,;:!?'"]|$)/g;
      doiReg.lastIndex = startIndex;
      let match = doiReg.exec(text);
      if (match != null) {
        const cleaned = this.normalizeDOI(match[2]);
        // 【2026-10】若抓到的是被括号截断的片段（如 "10.1002/(sici"，
        // 说明这实际是 SICI 型 DOI，应让位给下面的兜底正则处理，
        // 否则会以残缺标识符去查重，必然查不到并导致重复导入。
        if (!/\/[^/]*\($/.test(cleaned) && this.isValidDOI(cleaned)) {
          match.identifierType = 'doi';
          match.identifier = cleaned;
          return match;
        }
      }

      // 【2026-10 补充】SICI 型 DOI 内含成对括号（如 Wiley 的
      // 10.1002/(SICI)1097-0258(19980815)17:15<1661::AID-SIM968>3.0.CO;2-2），
      // 会被主正则的括号排除集截断而漏检，因此用宽松规则单独兜底。
      // 注意：这里用贪婪的 \S+ 而非 \S+? —— 惰性会在 SICI 的第一个 ')' 处截断；
      // 贪婪匹配由后视字符集（空白/引号/句点等真正的结束位置）来确定边界。
      const siciReg = /(\s|>|:|^|;|,|\/|\(|\[|"|')(10\.\d{4,9}\/\S+)(\s|["').,;:!]|$)/g;
      siciReg.lastIndex = startIndex;
      const siciMatch = siciReg.exec(text);
      if (siciMatch != null) {
        const cleaned = this.normalizeDOI(siciMatch[2]);
        if (this.isValidDOI(cleaned)) {
          siciMatch.identifierType = 'doi';
          siciMatch.identifier = cleaned;
          return siciMatch;
        }
      }
      
      // PMID检测
      // 匹配 "PMID: 1234567" 或 "PMID 1234567" 等格式 (7到8位数字)
      const pmidReg = /PMID\s*:?\s*(\d{7,8})/gi;
      pmidReg.lastIndex = startIndex;
      const pmidMatch = pmidReg.exec(text);
      if (pmidMatch != null) {
        pmidMatch.identifierType = 'pmid';
        pmidMatch.identifier = pmidMatch[1]; // 提取出括号里捕获的纯数字
        return pmidMatch;
      }

      return null;
    } catch (e) {
      console.warn('标识符检测出错:', e);
      return null;
    }
  }

  // 节点扫描逻辑
  scanNode(node) {
    try {
      if (!node.childNodes) return;
      if (['textarea', 'script', 'style', 'javascript'].includes(node.nodeName.toLowerCase())) return;
      if (!node.innerHTML) return;

      const innerHTML = node.innerHTML;
      
      // 改进的预检查逻辑
      const contentToCheck = node.outerHTML || node.innerHTML || '';
      const match = this.getAnyIdentifier(contentToCheck, 0);
      const isPubMedContainer = contentToCheck.includes('docsum-pmid') || contentToCheck.includes('PubMed ID') || contentToCheck.includes('current-id');
      
      if (match == null && !isPubMedContainer) {
        return;
      }

      // 扫描文本节点
      for (let i = 0; i < node.childNodes.length; i++) {
        const child = node.childNodes[i];

        if (child.hasXsslPickerIcon) {
          continue;
        }
        if (child.noXsslPicker) {
          continue;
        }
        if (child.tagName != null) {
          const tag = child.tagName.toLowerCase();
          switch (tag) {
            case 'input':
            case 'script':
            case 'textarea':
            case 'style':
            case 'map':
              continue;
          }
        }
        if (child.classList != null && child.classList.contains('ace_editor')) {
          continue;
        }

        if (child.nodeType === 3) { // 文本节点
          this.processTextNodeXsslStyle(child, node);
        } else if (child.nodeType === 1) { // 元素节点
          this.scanNode(child);
        }
      }

      // 处理插入的标记
      this.processInsertedMarkers(node);
    } catch (e) {
      console.error('扫描节点出错:', e);
    }
  }

  // 基于Xssl方式处理文本节点
  processTextNodeXsslStyle(textNode, parentNode) {
    try {
      const nodeValue = textNode.nodeValue;
      if (!nodeValue) return;

      let searchIndex = 0;
      let identifierCounter = 0;

      while (true) {
        let identifierMatch = this.getAnyIdentifier(nodeValue, searchIndex);
        
        // 针对 PubMed 网站特殊的 DOM 结构进行识别
        if (!identifierMatch && parentNode) {
          const isPubMedNode = 
            (parentNode.className && typeof parentNode.className === 'string' && 
             (parentNode.className.includes('docsum-pmid') || parentNode.className.includes('current-id'))) || 
            parentNode.title === 'PubMed ID';
            
          if (isPubMedNode) {
            // PubMed 把纯数字放在这个标签里，这里直接提取 7-8 位纯数字
            const numRegex = /(\d{7,8})/;
            const substr = nodeValue.substring(searchIndex);
            const match = numRegex.exec(substr);
            
            if (match) {
              identifierMatch = match;
              identifierMatch.index = searchIndex + match.index; // 修正相对于整个 nodeValue 的索引
              identifierMatch.identifierType = 'pmid';
              identifierMatch.identifier = match[1];
            }
          }
        }
        // 识别结束
        if (!identifierMatch) break;

        identifierCounter++;
        let diff = 0;
        let match = null;
        let title = 'Add to Zotero';
        let identifierType = 'unknown';


        // 确定标识符类型和值（直接信任前一步计算好的类型和纯净值）
        identifierType = identifierMatch.identifierType;
        let identifier = identifierMatch.identifier.replace(/\s/g, ''); // 提取出的纯净数字或字符
        
        if (identifierType === 'doi') {
          title = 'Add to Zotero by DOI';
          // 【2026-10 修正】插入位置必须用"页面上实际占用的字符数"来算，
          // 即正则原始匹配串 match[2]（含尾标点），而不是清洗后的 identifier
          // （已剥离尾标点，长度更短）。若用清洗值计算，图标会插到标识符中间。
          match = identifierMatch[2] || identifierMatch[0];
        } else if (identifierType === 'pmid') {
          title = 'Add to Zotero by PMID';
          match = identifierMatch[0]; // 使用整个正则匹配串(如"PMID: 1234567")来计算插入位置
        } else {
          title = 'Add to Zotero by ISBN';
          match = identifierMatch[2] || identifierMatch[0];
        }

        let insertIndex = identifierMatch.index + match.length - diff;
        if (nodeValue.length > insertIndex) insertIndex++;

        // 检查是否为电话号码
        if (/tel\.|phon/gi.test(nodeValue) || /^\+\d\d\s/.test(nodeValue)) {
          searchIndex = identifierMatch.index + match.length - diff;
          continue;
        }


        // 检查是否已存在
        const uniqueKey = `${identifierType}:${identifier}`;
        if (this.processedIdentifiers.has(uniqueKey)) {
          searchIndex = insertIndex;
          continue;
        }

        const insertData = ` %ZOTEROPICKER£${identifier}£${identifierType}£${title}£%`;

        if (parentNode.querySelector(`img[identifier='${identifier}']`) !== null) {
          break;
        }
        if (parentNode.parentNode && parentNode.parentNode.querySelector(`img[identifier='${identifier}']`) !== null) {
          break;
        }

        textNode.insertData(insertIndex, insertData);
        searchIndex = identifierMatch.index + match.length + insertData.length - diff;
        parentNode.hasXsslPickerIcon = true;
      }
    } catch (e) {
      console.warn('处理文本节点出错:', e);
    }
  }

  processInsertedMarkers(node) {
    try {
      const innerHTML = node.innerHTML;
      if (!innerHTML.includes('%ZOTEROPICKER')) return;

      // 使用正则表达式查找和替换标记
      const regex = /%ZOTEROPICKER£(.+?)£(.+?)£(.+?)£%/g;
      let newHTML = innerHTML;
      
      // 收集所有匹配项
      const matches = [...innerHTML.matchAll(regex)];
      
      // 为每个匹配项创建替换内容
      for (const match of matches) {
        const [fullMatch, identifier, type, title] = match;
        
        let processedIdentifier = identifier;
        
        // 处理ISBN和DOI的空格
        if (type === 'isbn' || type === 'doi') {
          processedIdentifier = processedIdentifier.replace(/\s/g, '');
        }
        
        const placeholderId = `zotero-placeholder-${Math.random().toString(36).substr(2, 9)}`;
        newHTML = newHTML.replace(fullMatch, `<span id="${placeholderId}"></span>`);
        
        // 使用setTimeout确保DOM更新后再创建元素
        setTimeout(() => {
          const placeholder = document.getElementById(placeholderId);
          if (placeholder) {
            this.createPickerNodeSync(placeholder, {
              value: processedIdentifier,
              type: type,
              title: title
            });
          }
        }, 0);
      }
      
      if (newHTML !== innerHTML) {
        node.innerHTML = newHTML;
      }
    } catch (e) {
      console.error('处理标记出错:', e);
    }
  }

  /**
   * 阻断事件的默认行为与冒泡。
   *
   * 【2026-10 修复·"点击 add 打开新网页"的根因】
   * 标记是被 insertData() 插进页面原有文本节点的，因此它常常落在宿主页面的
   * <a href="..."> 与 <form> 内部。点击我们插入的 ➕ / ✕ 时：
   *   ① <button> 未显式设置 type，HTML 默认 type=submit
   *      → 若祖先有 <form>，点击会**提交表单**，浏览器跳转到新页面；
   *   ② 事件继续冒泡到祖先 <a>
   *      → 触发链接导航，同样打开新网页。
   * 表现为"点一下 ➕ 就跳到一个新页面"。这里统一拦掉，
   * 只保留我们自己注册的 handler。
   */
  suppressEvent(e) {
    if (!e) return;
    e.preventDefault();
    e.stopPropagation();
  }

  /**
   * 判断事件是否由我们自己的"跳转链接"(🔍) 触发。
   *
   * 【2026-10 回归修复·务必保留】
   * 上一版在 wrapper 上用捕获阶段统一 suppressEvent，结果把 🔍 也一起拦死了：
   * 捕获阶段先于目标元素执行，`preventDefault()` 取消了 <a href="zotero://...">
   * 的默认导航，`stopPropagation()` 又让事件根本到不了 🔍 自身。
   * 表现为"点击查看标识完全没反应"。
   *
   * 正确做法：捕获阶段只拦"我们自己不可交互的部分"(wrapper 空白/✕/➕)，
   * 凡是来自 🔍 的事件一律放行，让浏览器执行 zotero:// 跳转；
   * 同时🔍 自身 handler 里继续 stopPropagation，阻止冒泡到宿主页面的 <a>。
   */
  isOwnOpenLink(e) {
    if (!e || !e.target || !e.target.closest) return false;
    return e.target.closest('a.zotero-open-link') !== null;
  }

  /**
   * 生成"跳到子分类"的链接元素（统一出口）。
   */
  createOpenLink(item) {
    const openLink = document.createElement('a');
    openLink.href = this.buildZoteroLink(item);
    openLink.className = 'zotero-open-link';
    openLink.style.cssText = 'margin-left: 2px; text-decoration: none; font-size: 12px;';
    openLink.title = item.collection && item.collection.path
      ? `在 Zotero 中打开（分类：${item.collection.path}）`
      : 'Open in Zotero';
    openLink.textContent = '🔍';
    // 【关键】只 stopPropagation，**绝不能 preventDefault**：
    // stopPropagation 阻止冒泡到宿主页面的 <a>（避免打开宿主网页），
    // 但保留默认行为让浏览器执行 zotero:// 协议跳转。
    openLink.addEventListener('click', (e) => {
      e.stopPropagation();
    });
    return openLink;
  }

  // 同步版本的创建选择器节点，避免异步问题
  async createPickerNodeSync(placeholder, identifier) {
    try {
      const uniqueKey = `${identifier.type}:${identifier.value}`;
      if (this.processedIdentifiers.has(uniqueKey)) {
        placeholder.remove();
        return;
      }

      this.processedIdentifiers.add(uniqueKey);

      // 检查Zotero状态
      const response = await this.checkZotero(identifier.type, identifier.value);

      // 创建包装元素
      const wrapper = document.createElement('span');
      wrapper.className = 'zotero-picker-wrapper';
      wrapper.style.cssText = 'margin-left: 2px; display: inline-flex; align-items: center; vertical-align: middle;';
      // 【2026-10】记录该标记对应的标识符，供 forceRefresh() 定位并重查
      wrapper.dataset.zpType = identifier.type;
      wrapper.dataset.zpIdentifier = identifier.value;
      // 标记插在页面文本里，落在宿主 <a>/<form> 内时必须整体接管，
      // 否则任何一次点击都会触发宿主页面的跳转或表单提交。
      //
      // 【2026-10 修正·两处关键细节，务必保留】
      // ① 捕获阶段必须放行来自 🔍 的事件：捕获先于目标执行，
      //    若这里无条件 preventDefault，会把 zotero:// 协议跳转一起取消
      //    （曾导致"点击查看标识完全没反应"）。
      // ② 捕获阶段**只 preventDefault，绝不 stopPropagation**：
      //    stopPropagation 会连同"继续向目标传播"一起终止，
      //    事件根本到不了 ➕ 自己的 handler，导入功能会静默失效
      //    （曾导致"点 ➕ 没反应"）。阻止冒泡由各元素自己的冒泡 handler 负责。
      wrapper.addEventListener('click', (e) => {
        if (this.isOwnOpenLink(e)) return;
        e.preventDefault();
      }, true);
      wrapper.addEventListener('mousedown', (e) => {
        if (this.isOwnOpenLink(e)) return;
        // mousedown 的 preventDefault 可阻止文本选区/拖拽，顺带也阻止宿主行为
        e.preventDefault();
      }, true);

      // 创建状态标记
      const marker = document.createElement('span');
      this.updateMarkerStyle(marker, response);
      // ✕ / ✓ 本身不可交互，但仍要 preventDefault，否则点在宿主 <a> 内会跳转。
      // 同样不能用 stopPropagation —— 它会掐断后面 ➕/🔍 的事件。
      marker.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();   // ✕ 是叶子节点，止于此处不会影响兄弟节点
      }, true);

      wrapper.appendChild(marker);

      // 添加功能按钮
      if (this.serviceAvailable) {
        if (response.exists && response.items && response.items[0]) {
          const item = response.items[0]; // 获取当前文献对象
          wrapper.appendChild(this.createOpenLink(item));
        } else {
          const addButton = document.createElement('button');
          addButton.className = 'zotero-add-button';
          addButton.style.cssText = 'margin-left: 2px; border: none; background: none; font-size: 12px; cursor: pointer; padding: 0;';
          // 【关键】显式声明 type="button"。缺省时 HTML 规范默认 submit，
          // 祖先若有 <form>，点击会提交表单 → 浏览器打开新页面。
          addButton.setAttribute('type', 'button');
          addButton.textContent = '➕';
          addButton.title = 'Add to Zotero';

          const handleClick = this.debounce(async (e) => {
            // 只 preventDefault：阻断宿主 <form> 提交 / <a> 导航。
            // 不调用 stopPropagation —— 这里已是事件目标附近，
            // 无需再阻断传播，贸然阻断可能影响同节点的其他监听。
            if (e) e.preventDefault();
            await this.importItem(identifier.type, identifier.value, addButton, wrapper, marker);
          }, this.debounceDelay);

          addButton.addEventListener('click', handleClick);
          wrapper.appendChild(addButton);
        }
      }

      // 替换占位符
      placeholder.parentNode.replaceChild(wrapper, placeholder);
    } catch (e) {
      console.error('创建选择器节点出错:', e);
      if (placeholder && placeholder.parentNode) {
        placeholder.remove();
      }
    }
  }

  // 基于参考代码的ISBN验证逻辑
  scanISBN10(S, f) {
    let t = 0, j, c;
    for (j = 0; j < S.length; j++) {
      c = S.charCodeAt(j);
      if ((c == 88 && f == 1) || (c == 120 && f == 1)) {
        t += 10;
        f--;
      }
      if (c > 47 && c < 58) {
        t += (c - 48) * f--;
      }
    }
    return { F: f, T: t };
  }

  isISBN10(isbn) {
    const { F, T } = this.scanISBN10(isbn, 10);
    return F == 0 && T % 11 == 0;
  }

  scanISBN13(S) {
    let f = 13, t = 0, j, c, k = 1;
    for (j = 0; j < S.length; j++) {
      c = S.charCodeAt(j);
      if (c > 47 && c < 58) {
        f--;
        t += (c - 48) * (2 + (k = -k));
      }
    }
    return { F: f, T: t };
  }

  isISBN13(isbn) {
    const { F, T } = this.scanISBN13(isbn);
    return F == 0 ? T % 10 == 0 : false;
  }

  isISBN(isbn) {
    if (!isbn || isbn.length < 10) return false;
    return this.isISBN10(isbn) || this.isISBN13(isbn);
  }

  normalizeDOI(doi) {
    if (!doi) return '';
    // 【2026-10】加强清洗：剥离尾部标点（正则边界改进后仍需兜底，
    // 例如 "10.x/y." 句末点号、"10.x/y," 逗号、"10.x/y)" 括号）
    return doi.trim()
      .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '')
      .replace(/^doi:\s*/i, '')
      .replace(/[\s.,;:!?)\]}'"]+$/, '')
      .toLowerCase();
  }

  // 提取到的 DOI 是否为合法形态（10.xxxx/yyyy，前缀 4-9 位数字）
  isValidDOI(doi) {
    if (!doi) return false;
    const d = this.normalizeDOI(doi);
    if (!d) return false;
    // 必须形如 10.NNNN/suffix
    return /^10\.\d{4,9}\/\S+$/.test(d);
  }

  normalizeISBN(isbn) {
    if (!isbn) return '';
    let ident = isbn.trim()
      .replace(/^isbn(?:-1[03])?\s*(?::|=|\s)\s*/i, '')
      .replace(/[^0-9X]/gi, '')
      .toUpperCase();
    
    if (ident.length !== 10 && ident.length !== 13) {
      return '';
    }
    
    return this.isISBN(ident) ? ident : '';
  }

  async init() {
    await this.checkServiceStatus();
    console.log('使用优化的页面扫描算法');
    this.scanFullPage();
    this.setupObserver();
  }

  async checkServiceStatus() {
    try {
      // 【2026-10】改用后端新增的 /health 端点。
      // 原先用 ?type=doi&identifier=test 探测，该请求会进入 DOI 校验分支并返回 400，
      // 语义不清且会做一次无意义的数据库查询。
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      const response = await fetch('http://127.0.0.1:5000/health', { signal: controller.signal });
      clearTimeout(timeoutId);
      this.serviceAvailable = response.ok;
      if (!this.serviceAvailable) {
        console.warn('Zotero Picker 后端返回异常状态');
      }
    } catch (error) {
      this.serviceAvailable = false;
      console.warn('Flask service is not available:', error);
    }
  }

  // 基于Xssl优化的页面扫描逻辑
  scanFullPage() {
    try {
      if (!document.body) return;
      
      // 扫描逻辑
      for (let i = 0; i < document.body.childNodes.length; i++) {
        const child = document.body.childNodes[i];
        const innerHTML = child.innerHTML;

        if (innerHTML === undefined) {
          continue;
        }
        // 改进的预检查
        const contentToCheck = child.outerHTML || child.innerHTML || '';
        const match = this.getAnyIdentifier(contentToCheck, 0);
        // 把 current-id 也加进白名单
        const isPubMedContainer = contentToCheck.includes('docsum-pmid') || contentToCheck.includes('PubMed ID') || contentToCheck.includes('current-id');
        
        // 如果既没有标准标识符，也不属于 PubMed 容器，才跳过
        if (match == null && !isPubMedContainer) {
          continue;
        }
        
        this.scanNode(child);
      }
    } catch (e) {
      console.error('扫描页面时出错:', e);
    }
  }

  updateMarkerStyle(marker, response) {
    let style;
    
    if (!this.serviceAvailable) {
      style = this.styles.marker.offline;
    } else {
      style = this.styles.marker[response.exists ? 'exists' : 'new'];
    }

    marker.className = `zotero-marker ${response.exists ? 'exists' : 'new'}`;
    marker.textContent = style.text;
    marker.style.cssText = `
      color: ${style.color};
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      font-size: 12px;
      font-weight: bold;
      line-height: 1;
      font-family: Arial, sans-serif;
      vertical-align: middle;
    `;
    marker.title = style.title;
  }

  async importItem(type, identifier, addButton, wrapper, marker) {
    try {
      addButton.disabled = true;
      addButton.style.opacity = '0.5';
      const originalText = addButton.textContent;
      addButton.textContent = '⏳'; // 变成沙漏，提示用户正在后台处理

      console.log(`尝试导入 ${type.toUpperCase()}:`, identifier);
      const response = await chrome.runtime.sendMessage({
        action: 'importItem',
        type: type,
        identifier: identifier
      });

      if (response && response.success) {
        const cacheKey = `${type}:${identifier}`;
        let newCheckResult = { exists: false };
        let verifiedItem = null;

        // 【2026-10 优化】后端在导入成功后已通过 Zotero HTTP API 实时校验并回传
        // 真实 itemKey（sqlite 快照读不到刚写入的 WAL 数据，轮询必然失败）。
        // 若拿到校验结果，直接使用，无需轮询。
        if (response.verified && response.items && response.items.length > 0) {
          verifiedItem = response.items[0];
          this.checkCache.set(cacheKey, {
            data: { exists: true, items: response.items },
            timestamp: Date.now()
          });
        } else {
          // 兜底：后端未确认时仍轮询查重接口
          let attempts = 0;
          const maxAttempts = 5;

          while (attempts < maxAttempts) {
            await new Promise(resolve => setTimeout(resolve, 500));
            this.checkCache.delete(cacheKey);
            newCheckResult = await this.checkZotero(type, identifier);

            if (newCheckResult.exists && newCheckResult.items && newCheckResult.items.length > 0) {
              console.log(`成功从数据库抓取到新文献！耗时: ~${(attempts + 1) * 0.5}秒`);
              break;
            }
            attempts++;
            console.log(`等待 Zotero 写入数据库... 第 ${attempts} 次尝试`);
          }
          if (newCheckResult.exists && newCheckResult.items && newCheckResult.items.length > 0) {
            verifiedItem = newCheckResult.items[0];
          }
        }

        if (verifiedItem) {
          // 已确认入库：立即更新 UI 为绿色对号并移除添加按钮
          this.updateMarkerStyle(marker, { exists: true });
          addButton.remove();

          const item = verifiedItem;
          wrapper.appendChild(this.createOpenLink(item));
        } else {
          // 未确认（Zotero 可能仍在处理）：保持按钮可点，避免用户误以为失败而重复导入
          addButton.disabled = false;
          addButton.style.opacity = '1';
          addButton.textContent = originalText;
          console.warn('导入指令已发送，但未确认入库状态，请稍后刷新查看。');
        }
      } else {
        // 导入指令发送失败
        addButton.disabled = false;
        addButton.style.opacity = '1';
        addButton.textContent = originalText;
        alert('导入失败，请检查Zotero运行状态或网络连接。');
      }
    } catch (error) {
      console.error('导入出错:', error);
      addButton.disabled = false;
      addButton.style.opacity = '1';
      addButton.textContent = '➕'; // 报错恢复原样
    }
  }

  // 设置页面变化监听器
  setupObserver() {
    if (typeof MutationObserver === 'undefined') return;

    const observer = new MutationObserver((mutations) => {
      try {
        const relevantMutation = mutations.find((mutation) => {
          const target = mutation.target;
          
          // 忽略我们自己的修改
          if (target.id === 'zotero-picker-panel' || 
              target.className?.includes('zotero-picker')) {
            return false;
          }

          return true;
        });

        if (!relevantMutation || this.observeTimeout !== null) return;

        window.clearTimeout(this.observeTimeout);
        this.observeTimeout = window.setTimeout(() => {
          try {
            this.scanNode(document.body);
          } catch (e) {
            console.error('Observer处理出错:', e);
          } finally {
            this.observeTimeout = null;
          }
        }, 2000);
      } catch (e) {
        console.error('MutationObserver出错:', e);
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  async checkZotero(type, identifier) {
    try {
      const cacheKey = `${type}:${identifier}`;
      const cachedResult = this.checkCache.get(cacheKey);
      if (cachedResult && (Date.now() - cachedResult.timestamp < this.cacheExpiration)) {
        return cachedResult.data;
      }

      console.log(`检查 ${type.toUpperCase()}（通过本地Flask）:`, identifier);
      const response = await chrome.runtime.sendMessage({
        action: 'checkIdentifier',
        type: type,
        identifier: identifier
      });
      
      this.checkCache.set(cacheKey, {
        data: response,
        timestamp: Date.now()
      });

      return response;
    } catch (error) {
      console.error(`Zotero检查失败(${type}):`, error);
      return { exists: false, error: error.message };
    }
  }

  /**
   * 生成 Zotero 跳转链接（优先跳到条目所在子分类）。
   *
   * 【格式依据】Zotero 10 源码
   *   C:\Program Files\Zotero\app\omni.ja
   *   → chrome/content/zotero/ZoteroProtocolHandler.mjs 的 SelectExtension
   * 支持的路由：
   *   {library|groups/:groupID}/collections/{colKey}/items/{itemKey}  ← 先选中分类再选中条目
   *   {library|groups/:groupID}/items/{itemKey}                    ← 只选中条目
   *   items/{libraryID}_{itemKey}                                  ← 官方已标注 Deprecated
   *
   * 处理时若能定位分类，会先 selectCollection() 再 selectItems()，
   * Zotero 直接展开到那个分类并高亮条目，比只跳到文库根节点省一步。
   *
   * 个人文库用 library/ 前缀；群组库用 groups/{groupID}/ 前缀。
   * ⚠ groupID 来自后端 groups 表（groups.groupID），不是 libraries.libraryID
   *（本库分别是 6212837 和 8）。官方 SelectExtension 内部会做
   *getLibraryIDFromGroupID() 转换，若传libraryID 会定位不到库。
   */
  buildZoteroLink(item) {
    if (!item || !item.itemKey) return '';
    const col = item.collection;
    const isGroup = item.libraryType === 'group' || item.groupID != null;

    // 群组库：groups/{groupID}/...
    if (isGroup && item.groupID) {
      const gid = item.groupID;
      if (col && col.key) {
        return `zotero://select/groups/${gid}/collections/${col.key}/items/${item.itemKey}`;
      }
      return `zotero://select/groups/${gid}/items/${item.itemKey}`;
    }

    // 个人文库
    if (col && col.key) {
      return `zotero://select/library/collections/${col.key}/items/${item.itemKey}`;
    }
    return `zotero://select/library/items/${item.itemKey}`;
  }

  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }
}

// 初始化
function safeInitZoteroPicker(label = 'init') {
  try {
    console.log(`[ZoteroPicker] ${label}`);
    new ZoteroPicker().init();
  } catch (e) {
    console.error('ZoteroPicker 初始化失败:', e);
  }
}

function setupZoteroInit() {
  // ✅ 1. 初次尝试：DOMContentLoaded 尽早处理
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => safeInitZoteroPicker('DOMContentLoaded'));
  } else {
    safeInitZoteroPicker('interactive/early');
  }

  // ✅ 2. 兜底：等待所有资源加载完成（适配 dynamic 页面）
  window.addEventListener('load', () => {
    setTimeout(() => safeInitZoteroPicker('window.load'), 1000); // 稍微延迟，确保懒加载完成
  });

  // ✅ 3. 二次兜底：某些站点如 ScienceDirect 加载晚，延时再尝试一次（如10秒后）
  setTimeout(() => safeInitZoteroPicker('timeout10s'), 10000);

  // ✅ 4. 可选增强：监听 SPA 页面导航（例如 PubMed 搜索后切换文章详情页）
  window.addEventListener('popstate', () => safeInitZoteroPicker('popstate'));
}

setupZoteroInit();
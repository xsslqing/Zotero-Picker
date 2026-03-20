class ZoteroPicker {
  constructor() {
    // 标识符检测模式
    this.identifierPatterns = this.initializePatterns();
    
    this.processedIdentifiers = new Set();
    this.observeTimeout = null;
    this.serviceAvailable = false;
    this.debounceDelay = 100;
    this.checkCache = new Map();
    this.cacheExpiration = 5 * 60 * 1000;
    
    // 样式配置
    this.styles = {
      marker: {
        new: { text: '✕', color: '#d52b1e', title: 'Not in Zotero - Click to add' },
        exists: { text: '✓', color: '#5dd95d', title: 'Exists in Zotero' },
        offline: { text: '!', color: '#999', title: 'Zotero service unavailable' }
      }
    };
    
    console.log('ZoteroPicker初始化 - 仅支持 DOI/ISBN/PMID');
  }

  initializePatterns() {
    return {
      // DOI检测模式 
      doi: [
        {
          regex: /(\s|\>|:|^|;|\/|,)(10\.\d\d\d+\/.+?)(\)\s|\s|\.\s|&nbsp;|\.$|\"|$)/g,
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
              isValid = identifier && identifier.indexOf('10.') !== -1;
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

      // DOI检测
      const doiReg = /(\s|\>|:|^|;|\/|,)(10\.\d\d\d+\/.+?)(\)\s|\s|\.\s|&nbsp;|\.$|\"|$)/g;
      doiReg.lastIndex = startIndex;
      let match = doiReg.exec(text);
      if (match != null) {
        match.identifierType = 'doi';
        match.identifier = match[2];
        return match;
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
          match = identifierMatch[2]; // DOI的占位符长度
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

      // 创建状态标记
      const marker = document.createElement('span');
      this.updateMarkerStyle(marker, response);

      wrapper.appendChild(marker);

      // 添加功能按钮
      if (this.serviceAvailable) {
        if (response.exists && response.items && response.items[0]) {
          const item = response.items[0]; // 获取当前文献对象
          const openLink = document.createElement('a');
          
          // 【终极修改方案：动态拼接真实的 libraryID】
          openLink.href = `zotero://select/items/${item.libraryID}_${item.itemKey}`;
          
          openLink.className = 'zotero-open-link';
          openLink.style.cssText = 'margin-left: 2px; text-decoration: none; font-size: 12px;';
          openLink.title = 'Open in Zotero';
          openLink.textContent = '🔍';
          wrapper.appendChild(openLink);
        } else {
          const addButton = document.createElement('button');
          addButton.className = 'zotero-add-button';
          addButton.style.cssText = 'margin-left: 2px; border: none; background: none; font-size: 12px; cursor: pointer; padding: 0;';
          addButton.textContent = '➕';
          addButton.title = 'Add to Zotero';
          
          const handleClick = this.debounce(async () => {
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
    return doi.trim()
      .replace(/\.$/, '')
      .toLowerCase()
      .replace(/\s+/g, '');
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
      const response = await fetch('http://127.0.0.1:5000/check_identifier?type=doi&identifier=test', {
        timeout: 2000
      });
      this.serviceAvailable = response.ok;
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
        let attempts = 0;
        const maxAttempts = 5; // 最多轮询 10 次

        // 核心修复：轮询机制。每隔 500 毫秒查一次数据库，最多等 5 秒
        while (attempts < maxAttempts) {
          // 强制等待 500ms
          await new Promise(resolve => setTimeout(resolve, 500));
          
          // 每次检查前必须清除缓存，保证查到的是最新鲜的数据库
          this.checkCache.delete(cacheKey);
          newCheckResult = await this.checkZotero(type, identifier);

          // 如果查到了，立刻跳出循环！
          if (newCheckResult.exists && newCheckResult.items && newCheckResult.items.length > 0) {
            console.log(`成功从数据库抓取到新文献！耗时: ~${(attempts + 1) * 0.5}秒`);
            break; 
          }
          
          attempts++;
          console.log(`等待 Zotero 写入数据库... 第 ${attempts} 次尝试`);
        }

        if (newCheckResult.exists) {
          // 查到了！更新 UI 为绿色对号，并添加跳转放大镜
          this.updateMarkerStyle(marker, newCheckResult);
          addButton.remove(); // 移除添加按钮
          
          if (newCheckResult.items && newCheckResult.items[0]) {
            const item = newCheckResult.items[0];
            const openLink = document.createElement('a');
            
            // 结合我们之前修复的精准跳转逻辑
            openLink.href = `zotero://select/items/${item.libraryID}_${item.itemKey}`;
            
            openLink.className = 'zotero-open-link';
            openLink.style.cssText = 'margin-left: 2px; text-decoration: none; font-size: 12px;';
            openLink.title = 'Open in Zotero';
            openLink.textContent = '🔍';
            wrapper.appendChild(openLink);
          }
        } else {
          // 如果等了 5 秒还没查到（可能是网太卡，Zotero下载太慢）
          addButton.disabled = false;
          addButton.style.opacity = '1';
          addButton.textContent = originalText;
          console.warn('导入指令已发送，但 Zotero 似乎处理得很慢，请稍后刷新查看。');
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
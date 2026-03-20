// 后台脚本
async function checkIdentifier(type, identifier) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);

  try {
    const response = await fetch(
      `http://127.0.0.1:5000/check_identifier?type=${type}&identifier=${encodeURIComponent(identifier)}`,
      { 
        signal: controller.signal,
        headers: {
          'Accept': 'application/json'
        }
      }
    );
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP错误! status: ${response.status}, message: ${errorText}`);
    }

    return await response.json();
  } catch (error) {
    clearTimeout(timeoutId);
    console.error('检查标识符错误:', error);
    return { 
      exists: false, 
      error: error.name === 'AbortError' ? '请求超时' : '服务连接失败' 
    };
  }
}

async function importItem(type, identifier) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);

  try {
    const response = await fetch('http://127.0.0.1:5000/import_item', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ type, identifier }),
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    
    const result = await response.json();
    return {
      success: result.success,
      message: result.message || (result.success ? '导入成功' : '导入失败，请检查Zotero运行状态。')
    };
  } catch (error) {
    clearTimeout(timeoutId);
    console.error('导入错误:', error);
    return { 
      success: false, 
      message: error.name === 'AbortError' ? '导入请求超时，请重试。' : `导入失败: ${error.message}`
    };
  }
}

// 监听来自内容脚本的消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'checkIdentifier') {
    checkIdentifier(request.type, request.identifier)
      .then(sendResponse)
      .catch(error => sendResponse({ 
        exists: false, 
        error: `检查失败: ${error.message}` 
      }));
    return true;
  }
  
  if (request.action === 'importItem') {
    importItem(request.type, request.identifier)
      .then(sendResponse)
      .catch(error => sendResponse({ 
        success: false, 
        message: `导入失败: ${error.message}` 
      }));
    return true;
  }
});
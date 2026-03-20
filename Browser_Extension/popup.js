document.addEventListener('DOMContentLoaded', async () => {
  const statusIcon = document.getElementById('serviceStatus');
  const statusText = document.getElementById('statusText');

  try {
    const response = await fetch('http://127.0.0.1:5000/check_identifier?type=doi&identifier=test', {
      timeout: 2000
    });
    
    if (response.ok) {
      statusIcon.className = 'status-icon online';
      statusText.textContent = 'Flask 服务正常运行';
    } else {
      throw new Error('服务响应异常');
    }
  } catch (error) {
    statusIcon.className = 'status-icon offline';
    statusText.textContent = 'Flask 服务未运行，请启动本地服务';
  }
}); 
/**
 * 基金分析系统 — 全局客户端脚本
 */

// 表单提交时显示加载状态
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('button[type="submit"]');
      if (btn && !btn.dataset.noLoading) {
        btn.disabled = true;
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<span class="loading-spinner me-1"></span>处理中…';
        // 防止长时间卡住时恢复按钮（15s 后恢复）
        setTimeout(() => {
          btn.disabled = false;
          btn.innerHTML = originalHtml;
        }, 15000);
      }
    });
  });

  // 自动关闭 alert 消息（5s）
  document.querySelectorAll('.alert.alert-success, .alert.alert-info').forEach(el => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

  // 为所有外部链接加 noopener 保护
  document.querySelectorAll('a[target="_blank"]').forEach(a => {
    if (!a.rel) a.rel = 'noopener noreferrer';
  });

  // 初始化术语说明弹层（点击感叹号显示）
  document.querySelectorAll('[data-bs-toggle="popover"]').forEach(el => {
    bootstrap.Popover.getOrCreateInstance(el, {
      container: 'body',
      sanitize: false,
    });
  });
});


// انتخاب خودکار محور متنی معنادار (به‌جای «ردیف») و شاخص عددی در کاوشگر پویای جداول
(() => {
  function smartPickExplorerSelects() {
    const axisSel = document.querySelector('select[id*="Axis"], select[id*="axis"], #dynAxisSelect, #biAxisSelect');
    const metricSel = document.querySelector('select[id*="Metric"], select[id*="metric"], #dynMetricSelect, #biMetricSelect');
    if (axisSel && axisSel.options.length > 1) {
      const curTxt = (axisSel.options[axisSel.selectedIndex]?.text || '').trim();
      if (curTxt.includes('ردیف') || curTxt.toLowerCase() === 'id') {
        const better = Array.from(axisSel.options).find(o => {
          const t = o.text.trim();
          return !t.includes('ردیف') && !t.includes('تعداد') && t.toLowerCase() !== 'id';
        });
        if (better) {
          axisSel.value = better.value;
          axisSel.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    }
    if (metricSel && metricSel.options.length > 1) {
      const curTxt = (metricSel.options[metricSel.selectedIndex]?.text || '').trim();
      if (curTxt.includes('تعداد رکورد')) {
        const betterM = Array.from(metricSel.options).find(o => o.text.includes('شرکت') || o.text.includes('مخاطب') || o.text.includes('تعداد'));
        if (betterM && !betterM.text.includes('تعداد رکورد')) {
          metricSel.value = betterM.value;
          metricSel.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    }
  }
  window.addEventListener('pywebviewready', () => setTimeout(smartPickExplorerSelects, 900));
  document.addEventListener('change', (e) => {
    if (e.target && e.target.tagName === 'SELECT' && (e.target.id || '').toLowerCase().includes('table')) {
      setTimeout(smartPickExplorerSelects, 250);
    }
  });
})();

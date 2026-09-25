/* 大周IM 附件渲染与在线预览
 * 依赖：buildAttachmentHtml(a) -> html 字符串（消息渲染接口）
 *       AttachmentPreview.text/docx/xlsx/office(url, containerId)  懒加载解析库
 */
(function () {
  'use strict';
  var seq = 0;
  var scriptCache = {};

  function esc(t) {
    var d = document.createElement('div');
    d.textContent = (t === null || t === undefined) ? '' : String(t);
    return d.innerHTML;
  }

  function loadScript(src, cb) {
    if (scriptCache[src]) { if (cb) cb(); return; }
    var s = document.createElement('script');
    s.src = src;
    s.onload = function () { scriptCache[src] = 1; if (cb) cb(); };
    s.onerror = function () { if (cb) cb(new Error('load fail: ' + src)); };
    document.head.appendChild(s);
  }

  function decodeText(buf) {
    var arr = new Uint8Array(buf);
    try { return new TextDecoder('utf-8', { fatal: true }).decode(arr); }
    catch (e) {
      try { return new TextDecoder('gbk').decode(arr); }
      catch (e2) { return new TextDecoder('utf-8').decode(arr); }
    }
  }

  /* 轻量 HTML 清洗：去脚本/危险标签与事件属性（用于 mammoth 输出的 docx 内容） */
  function sanitizeHtml(html) {
    var t = document.createElement('template');
    t.innerHTML = html;
    t.content.querySelectorAll('script,iframe,object,embed,link,meta,form,input,button,base').forEach(function (n) { n.remove(); });
    t.content.querySelectorAll('*').forEach(function (n) {
      [].slice.call(n.attributes).forEach(function (attr) {
        if (/^on/i.test(attr.name) || /expression\s*\(/i.test(attr.value)) n.removeAttribute(attr.name);
      });
    });
    return t.innerHTML;
  }

  function boxStyle(maxH) {
    return 'max-height:' + (maxH || 320) + 'px;overflow:auto;background:#fafafa;border:1px solid #e5e5e5;border-radius:6px;padding:8px;margin-top:6px;font-size:12px;word-break:break-all;';
  }

  function msgIn(id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }
  function msgTxt(id, txt) {
    var el = document.getElementById(id);
    if (el) el.textContent = txt;
  }
  function failBox(id, msg) {
    msgIn(id, '<div style="color:#c62828;padding:6px;">' + esc(msg) + '</div>');
  }

  var Preview = {
    text: function (url, id) {
      fetch(url).then(function (r) { if (!r.ok) throw 0; return r.arrayBuffer(); }).then(function (buf) {
        if (buf.byteLength > 500 * 1024) { msgTxt(id, '文件较大，已停止网页预览，请直接下载查看'); return; }
        var text = decodeText(buf);
        var pre = document.createElement('pre');
        pre.textContent = text;
        pre.style.cssText = 'white-space:pre-wrap;word-break:break-all;margin:0;font-family:ui-monospace,Menlo,Consolas,monospace;';
        var el = document.getElementById(id);
        if (el) { el.innerHTML = ''; el.appendChild(pre); el.style.cssText = boxStyle(280); }
      }).catch(function () { failBox(id, '文本预览失败，请下载查看'); });
    },
    docx: function (url, id) {
      loadScript('/static/chat/js/mammoth.browser.min.js', function (err) {
        if (err) { failBox(id, '预览组件加载失败，请下载查看'); return; }
        fetch(url).then(function (r) { if (!r.ok) throw 0; return r.arrayBuffer(); }).then(function (buf) {
          window.mammoth.convertToHtml({ arrayBuffer: buf }).then(function (res) {
            msgIn(id, '<div style="' + boxStyle(360) + '">' + sanitizeHtml(res.value) + '</div>');
          }).catch(function () { failBox(id, '文档解析失败（可能不是有效的 docx），请下载查看'); });
        }).catch(function () { failBox(id, '文档预览失败，请下载查看'); });
      });
    },
    xlsx: function (url, id) {
      loadScript('/static/chat/js/xlsx.full.min.js', function (err) {
        if (err) { failBox(id, '预览组件加载失败，请下载查看'); return; }
        fetch(url).then(function (r) { if (!r.ok) throw 0; return r.arrayBuffer(); }).then(function (buf) {
          var wb = window.XLSX.read(new Uint8Array(buf), { type: 'array' });
          var html = '';
          wb.SheetNames.forEach(function (name) {
            var ws = wb.Sheets[name];
            var rows = window.XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
            html += '<div style="font-weight:bold;margin:6px 0 2px;">' + esc(name) + '（' + rows.length + ' 行）</div>';
            html += '<table style="border-collapse:collapse;min-width:100%;">';
            rows.slice(0, 200).forEach(function (row, ri) {
              html += '<tr>';
              row.forEach(function (cell) {
                html += '<td style="border:1px solid #ddd;padding:3px 6px;' + (ri === 0 ? 'background:#f0f0f0;font-weight:600;' : '') + '">' + esc(cell) + '</td>';
              });
              html += '</tr>';
            });
            if (rows.length > 200) html += '<tr><td style="padding:6px;color:#888;">仅显示前 200 行，完整内容请下载查看</td></tr>';
            html += '</table>';
          });
          msgIn(id, '<div style="' + boxStyle(360) + '">' + html + '</div>');
        }).catch(function () { failBox(id, '表格解析失败（可能不是有效的 xlsx），请下载查看'); });
      });
    },
    office: function (url, id) {
      /* pptx/老版 office：跳转微软在线预览（公网可访问的媒体地址） */
      var src = 'https://view.officeapps.live.com/op/view.aspx?src=' + encodeURIComponent(url);
      window.open(src, '_blank');
    }
  };
  window.AttachmentPreview = Preview;

  var TEXT_EXTS = ['txt', 'md', 'csv', 'json', 'log', 'xml', 'yaml', 'yml', 'ini', 'conf'];
  var OFFICE_EXTS = ['pptx', 'ppt', 'doc', 'xls', 'xlsm', 'docm', 'odt', 'ods', 'rtf'];

  function dlLink(a) {
    return '<a class="att-dl" href="' + a.url + '" download="' + esc(a.name || '') + '" style="margin-left:8px;color:#1a73e8;font-size:12px;text-decoration:none;">下载</a>';
  }
  function previewBtn(label, fn, url) {
    var cid = 'pv' + (++seq);
    return '<button type="button" onclick="AttachmentPreview.' + fn + '(\'' + url + '\',\'' + cid + '\')" style="margin-left:8px;padding:2px 10px;font-size:12px;border:1px solid #1a73e8;background:#fff;color:#1a73e8;border-radius:12px;cursor:pointer;">' + label + '</button><div id="' + cid + '"></div>';
  }

  window.buildAttachmentHtml = function (a) {
    if (!a) return '';
    var ext = (a.name || '').split('.').pop().toLowerCase();
    var dl = dlLink(a);
    /* 图片 */
    if (a.type === 'image' || ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].indexOf(ext) >= 0) {
      return '<div class="attachment"><img src="' + a.url + '" alt="附件" style="max-width:220px;max-height:220px;border-radius:6px;display:block;cursor:pointer;" onclick="window.open(\'' + a.url + '\',\'_blank\')"><div class="att-actions" style="margin-top:4px;">' + dl + '</div></div>';
    }
    /* 音频 */
    if (a.type === 'audio' || ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac', 'wma', 'opus'].indexOf(ext) >= 0) {
      return '<div class="attachment"><audio controls preload="metadata" src="' + a.url + '" style="width:100%;max-width:280px;height:40px;"></audio><div class="att-actions" style="margin-top:4px;">' + esc(a.name || '音频') + dl + '</div></div>';
    }
    /* 视频 */
    if (a.type === 'video' || ['mp4', 'webm', 'mov', 'm4v', 'avi', 'mkv', 'flv'].indexOf(ext) >= 0) {
      return '<div class="attachment"><video controls preload="metadata" src="' + a.url + '" style="max-width:100%;max-height:320px;border-radius:6px;"></video><div class="att-actions" style="margin-top:4px;">' + esc(a.name || '视频') + dl + '</div></div>';
    }
    /* PDF：内嵌预览 */
    if (a.type === 'pdf' || ext === 'pdf') {
      return '<div class="attachment"><div style="font-size:12px;color:#888;">' + esc(a.name || 'PDF') + '</div><iframe src="' + a.url + '" style="width:100%;max-width:340px;height:280px;border:1px solid #e0e0e0;border-radius:6px;margin-top:4px;"></iframe><div class="att-actions" style="margin-top:4px;">' + dl + '</div></div>';
    }
    /* 纯文本：内嵌自动预览（后端已统一转为 UTF-8，中文不乱码） */
    if (a.type === 'text' || TEXT_EXTS.indexOf(ext) >= 0) {
      return '<div class="attachment"><div style="font-size:12px;color:#888;">' + esc(a.name || '文本') + '</div><iframe src="' + a.url + '" style="width:100%;max-width:340px;height:200px;border:1px solid #e0e0e0;border-radius:6px;margin-top:4px;background:#fff;"></iframe><div class="att-actions" style="margin-top:4px;">' + dl + '</div></div>';
    }
    /* docx：本地解析预览 */
    if (a.type === 'docx' || ext === 'docx') {
      return '<div class="attachment"><div style="font-size:12px;color:#888;">' + esc(a.name || '文档') + previewBtn('文档预览', 'docx', a.url) + '</div>' + dl + '</div>';
    }
    /* xlsx：本地解析预览 */
    if (a.type === 'xlsx' || ext === 'xlsx') {
      return '<div class="attachment"><div style="font-size:12px;color:#888;">' + esc(a.name || '表格') + previewBtn('表格预览', 'xlsx', a.url) + '</div>' + dl + '</div>';
    }
    /* 其他 Office：微软在线预览 */
    if (a.type === 'office' || OFFICE_EXTS.indexOf(ext) >= 0) {
      return '<div class="attachment"><div style="font-size:12px;color:#888;">' + esc(a.name || 'Office 文档') + previewBtn('在线预览', 'office', a.url) + '</div>' + dl + '</div>';
    }
    /* 兜底：下载 */
    return '<div class="attachment"><a href="' + a.url + '" target="_blank">' + esc(a.name || '附件') + '</a>' + dl + '</div>';
  };

  /* 服务端渲染占位自动扫描：历史消息在服务端只输出占位 div，页面加载后统一用 buildAttachmentHtml 渲染 */
  function hydrateServerAttachments() {
    var nodes = document.querySelectorAll('.attachment[data-url]');
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var a = {
        url: n.getAttribute('data-url'),
        name: n.getAttribute('data-name') || '',
        type: n.getAttribute('data-type') || ''
      };
      n.outerHTML = window.buildAttachmentHtml(a);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hydrateServerAttachments);
  } else {
    hydrateServerAttachments();
  }
})();

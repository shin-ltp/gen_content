// notify-email.mjs — Gate/信源異常のGmail SMTP通知（依存ゼロ・Node標準TLSのみ）
// 実行は node --use-system-ca を前提とする（Gmail証明書検証のため）。
import fs from 'node:fs';
import path from 'node:path';
import tls from 'node:tls';

const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//, '')), '..', '..');

function loadEnv() {
  const envPath = path.join(PROJECT, '.env');
  const env = {};
  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
      const m = line.match(/^([A-Z_]+)=(.*)$/);
      if (m) env[m[1]] = m[2].trim();
    }
  }
  return env;
}

function encodeHeader(s) {
  return '=?UTF-8?B?' + Buffer.from(s, 'utf8').toString('base64') + '?=';
}

class SmtpClient {
  constructor(socket) {
    this.socket = socket;
    this.waiter = null;
    this.buffer = '';
    socket.on('data', (chunk) => {
      this.buffer += chunk.toString('utf8');
      let idx;
      while ((idx = this.buffer.indexOf('\r\n')) >= 0) {
        const line = this.buffer.slice(0, idx);
        this.buffer = this.buffer.slice(idx + 2);
        const waiter = this.waiter;
        if (!waiter) continue;
        waiter.lines.push(line);
        if (/^\d{3} /.test(line)) {
          this.waiter = null;
          const code = parseInt(line.slice(0, 3), 10);
          if (waiter.expected.includes(code)) waiter.resolve({ code, lines: waiter.lines });
          else waiter.reject(new Error('SMTP ' + code + ': ' + waiter.lines.join(' / ')));
        }
      }
    });
    socket.on('error', (e) => {
      if (this.waiter) { const w = this.waiter; this.waiter = null; w.reject(new Error('SMTP socket: ' + e.message)); }
    });
  }
  response(expected, timeoutMs = 15000) {
    if (this.waiter) return Promise.reject(new Error('SMTP busy'));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this.waiter && this.waiter.timer === timer) this.waiter = null;
        reject(new Error('SMTP timeout (' + expected.join('/') + ')'));
      }, timeoutMs);
      this.waiter = {
        expected,
        lines: [],
        resolve: (v) => { clearTimeout(timer); resolve(v); },
        reject: (e) => { clearTimeout(timer); reject(e); },
        timer
      };
    });
  }
  async command(cmd, expected, timeoutMs = 15000) {
    const p = this.response(expected, timeoutMs);
    this.socket.write(cmd + '\r\n');
    return p;
  }
}

async function sendFailureNotification({ subject, text }) {
  const ENV = loadEnv();
  const user = ENV.GOOGLE_EMAIL || process.env.GOOGLE_EMAIL || '';
  const pass = ENV.GMAIL_APP_PASSWORD || process.env.GMAIL_APP_PASSWORD || '';
  const to = ENV.NOTIFY_EMAIL || process.env.NOTIFY_EMAIL || 'choshin.ltp@gmail.com';
  if (!user || !pass) throw new Error('GOOGLE_EMAIL / GMAIL_APP_PASSWORD 未設定');

  const socket = tls.connect({ host: 'smtp.gmail.com', port: 465, servername: 'smtp.gmail.com' });
  socket.setEncoding('utf8');
  const client = new SmtpClient(socket);
  const failOnce = new Promise((_, reject) => {
    socket.once('error', (e) => reject(new Error('SMTP socket: ' + e.message)));
  });
  try {
    await Promise.race([client.response([220]), failOnce]);
    await client.command('EHLO us-stock-daily', [250]);
    await client.command('AUTH LOGIN', [334]);
    await client.command(Buffer.from(user, 'utf8').toString('base64'), [334]);
    await client.command(Buffer.from(pass, 'utf8').toString('base64'), [235]);
    await client.command('MAIL FROM:<' + user + '>', [250]);
    await client.command('RCPT TO:<' + to + '>', [250, 251]);
    await client.command('DATA', [354]);
    const date = new Date().toUTCString();
    const bodyBase64 = Buffer.from(text, 'utf8').toString('base64').replace(/(.{76})/g, '$1\r\n ');
    const msg = [
      'From: us-stock-daily <' + user + '>',
      'To: <' + to + '>',
      'Subject: ' + encodeHeader(subject),
      'Date: ' + date,
      'MIME-Version: 1.0',
      'Content-Type: text/plain; charset=UTF-8',
      'Content-Transfer-Encoding: base64',
      '',
      bodyBase64
    ].join('\r\n');
    await client.command(msg.replace(/\r?\n\./g, '\r\n..') + '\r\n.', [250], 30000);
    await client.command('QUIT', [221]);
    return { to, messageId: date };
  } finally {
    socket.destroy();
  }
}

export { sendFailureNotification };

if (process.argv[1] && import.meta.url.endsWith(path.basename(process.argv[1])) && process.argv.includes('--test')) {
  sendFailureNotification({
    subject: '[TEST] us-stock-daily 通知渠道测试',
    text: '这是一封测试邮件。若收到，说明 Gate/信源异常通知配置正常。'
  }).then(r => {
    console.log('TEST MAIL OK -> ' + r.to);
  }).catch(e => {
    console.error('TEST MAIL FAIL: ' + e.message);
    process.exitCode = 1;
  });
}

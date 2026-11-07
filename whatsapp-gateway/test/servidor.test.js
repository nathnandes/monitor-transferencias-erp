'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { criarServidor, tokenConfere } = require('../src/servidor');

const TOKEN = 'token-de-teste-com-32-caracteres!';
const silencioso = { warn() {}, error() {} };

async function subir(sock) {
    const servidor = criarServidor({
        token: TOKEN,
        obterSock: () => sock,
        obterEstado: () => ({ estado: sock ? 'conectado' : 'aguardando_qr', numero: '' }),
        logger: silencioso,
    });
    await new Promise(resolve => servidor.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${servidor.address().port}`;
    return { base, fechar: () => new Promise(resolve => servidor.close(resolve)) };
}

function pedir(base, rota, { metodo = 'POST', corpo, token = TOKEN } = {}) {
    return fetch(`${base}${rota}`, {
        method: metodo,
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
}

function sockFalso({ existe = true, falhar = false } = {}) {
    const enviadas = [];
    return {
        enviadas,
        onWhatsApp: async numero => [{ exists: existe, jid: `${numero}@s.whatsapp.net` }],
        sendMessage: async (jid, conteudo) => {
            if (falhar) {
                throw new Error('Connection Closed');
            }
            enviadas.push({ jid, conteudo });
            return { key: { id: 'ABC123' } };
        },
    };
}

test('token curto impede o gateway de subir', () => {
    assert.throws(() => criarServidor({ token: 'curto', obterSock: () => null, obterEstado: () => ({}) }));
});

test('tokenConfere exige Bearer e o valor exato', () => {
    assert.equal(tokenConfere(`Bearer ${TOKEN}`, TOKEN), true);
    assert.equal(tokenConfere(`Bearer ${TOKEN}x`, TOKEN), false);
    assert.equal(tokenConfere(TOKEN, TOKEN), false);
    assert.equal(tokenConfere(undefined, TOKEN), false);
});

test('sem token ou com token errado responde 401 e nao envia', async () => {
    const sock = sockFalso();
    const g = await subir(sock);
    try {
        assert.equal((await pedir(g.base, '/enviar', { corpo: { numero: '5511999990000', texto: 'oi' }, token: '' })).status, 401);
        assert.equal((await pedir(g.base, '/enviar', { corpo: { numero: '5511999990000', texto: 'oi' }, token: 'x'.repeat(32) })).status, 401);
        assert.equal(sock.enviadas.length, 0);
    } finally {
        await g.fechar();
    }
});

test('envia o texto para o JID que o WhatsApp devolve', async () => {
    const sock = sockFalso();
    const g = await subir(sock);
    try {
        const resp = await pedir(g.base, '/enviar', { corpo: { numero: '5511999990000', texto: 'Alerta: teste' } });
        assert.equal(resp.status, 200);
        assert.deepEqual(await resp.json(), { id: 'ABC123' });
        assert.deepEqual(sock.enviadas, [{ jid: '5511999990000@s.whatsapp.net', conteudo: { text: 'Alerta: teste' } }]);
    } finally {
        await g.fechar();
    }
});

test('numero ou texto invalido responde 400', async () => {
    const g = await subir(sockFalso());
    try {
        assert.equal((await pedir(g.base, '/enviar', { corpo: { numero: '+55 92 9999', texto: 'oi' } })).status, 400);
        assert.equal((await pedir(g.base, '/enviar', { corpo: { numero: '5511999990000', texto: '  ' } })).status, 400);
        assert.equal((await pedir(g.base, '/enviar', { corpo: { numero: '5511999990000', texto: 'x'.repeat(5000) } })).status, 400);
    } finally {
        await g.fechar();
    }
});

test('desconectado responde 503; numero sem WhatsApp 422; falha no envio 502', async () => {
    const corpo = { numero: '5511999990000', texto: 'oi' };
    for (const [sock, status] of [[null, 503], [sockFalso({ existe: false }), 422], [sockFalso({ falhar: true }), 502]]) {
        const g = await subir(sock);
        try {
            assert.equal((await pedir(g.base, '/enviar', { corpo })).status, status);
        } finally {
            await g.fechar();
        }
    }
});

test('status informa o estado da conexao', async () => {
    const g = await subir(null);
    try {
        const resp = await pedir(g.base, '/status', { metodo: 'GET' });
        assert.equal(resp.status, 200);
        assert.equal((await resp.json()).estado, 'aguardando_qr');
    } finally {
        await g.fechar();
    }
});

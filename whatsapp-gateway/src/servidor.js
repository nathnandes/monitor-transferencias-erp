'use strict';



const http = require('node:http');
const { createHash, timingSafeEqual } = require('node:crypto');

const LIMITE_CORPO = 64 * 1024;
const LIMITE_TEXTO = 4096;

const NUMERO = /^\d{10,15}$/;

function tokenConfere(cabecalho, esperado) {
    const recebido = /^Bearer (.+)$/.exec(cabecalho || '')?.[1] || '';

    const a = createHash('sha256').update(recebido).digest();
    const b = createHash('sha256').update(esperado).digest();
    return recebido.length > 0 && timingSafeEqual(a, b);
}

function responder(res, status, corpo) {
    const json = JSON.stringify(corpo);
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(json);
}

function lerJson(req) {
    return new Promise((resolve, reject) => {
        let tamanho = 0;
        const partes = [];
        req.on('data', parte => {
            tamanho += parte.length;
            if (tamanho > LIMITE_CORPO) {
                reject(Object.assign(new Error('corpo grande demais'), { status: 400 }));
                req.destroy();
                return;
            }
            partes.push(parte);
        });
        req.on('end', () => {
            try {
                resolve(JSON.parse(Buffer.concat(partes).toString('utf8')));
            } catch {
                reject(Object.assign(new Error('JSON invalido'), { status: 400 }));
            }
        });
        req.on('error', reject);
    });
}


function criarServidor({ token, obterSock, obterEstado, logger = console }) {
    if (!token || token.length < 16) {
        throw new Error('WHATSAPP_GATEWAY_TOKEN precisa ter pelo menos 16 caracteres');
    }

    async function enviar(req, res) {
        let corpo;
        try {
            corpo = await lerJson(req);
        } catch (err) {
            return responder(res, err.status || 400, { erro: err.message });
        }
        const numero = typeof corpo?.numero === 'string' ? corpo.numero : '';
        const texto = typeof corpo?.texto === 'string' ? corpo.texto : '';
        if (!NUMERO.test(numero)) {
            return responder(res, 400, { erro: 'numero invalido: use DDI + DDD + numero, so digitos' });
        }
        if (!texto.trim() || texto.length > LIMITE_TEXTO) {
            return responder(res, 400, { erro: `texto vazio ou com mais de ${LIMITE_TEXTO} caracteres` });
        }

        const sock = obterSock();
        if (!sock) {
            return responder(res, 503, { erro: 'WhatsApp desconectado' });
        }
        try {

            const [resultado] = (await sock.onWhatsApp(numero)) || [];
            if (!resultado?.exists) {
                return responder(res, 422, { erro: 'numero sem WhatsApp' });
            }
            const enviada = await sock.sendMessage(resultado.jid, { text: texto });
            return responder(res, 200, { id: enviada?.key?.id || null });
        } catch (err) {
            logger.warn(`falha ao enviar para ...${numero.slice(-4)}: ${err.message}`);
            return responder(res, 502, { erro: 'falha ao enviar pelo WhatsApp' });
        }
    }

    return http.createServer((req, res) => {
        if (!tokenConfere(req.headers.authorization, token)) {
            return responder(res, 401, { erro: 'nao autorizado' });
        }
        const rota = `${req.method} ${(req.url || '').split('?')[0]}`;
        if (rota === 'GET /status') {
            return responder(res, 200, obterEstado());
        }
        if (rota === 'POST /enviar') {
            return enviar(req, res).catch(err => {
                logger.error(`erro inesperado: ${err.message}`);
                if (!res.headersSent) {
                    responder(res, 500, { erro: 'erro interno' });
                }
            });
        }
        return responder(res, 404, { erro: 'rota inexistente' });
    });
}

module.exports = { criarServidor, tokenConfere };

'use strict';



const fs = require('node:fs');
const path = require('node:path');



const envDoProjeto = process.env.GATEWAY_ENV_FILE || path.join(__dirname, '..', '..', '.env');
if (fs.existsSync(envDoProjeto)) {
    process.loadEnvFile(envDoProjeto);
}

const { criarConexao } = require('./conexao');
const { criarServidor } = require('./servidor');

const host = process.env.GATEWAY_HOST || '127.0.0.1';
const porta = Number(process.env.GATEWAY_PORT || 3100);
const authDir = path.resolve(process.env.GATEWAY_AUTH_DIR || path.join(__dirname, '..', 'auth'));

const conexao = criarConexao({ authDir, nivelLogBaileys: process.env.GATEWAY_LOG_BAILEYS || 'silent' });

let servidor;
try {
    servidor = criarServidor({
        token: process.env.WHATSAPP_GATEWAY_TOKEN || '',
        obterSock: conexao.obterSock,
        obterEstado: conexao.obterEstado,
    });
} catch (err) {
    console.error(err.message);
    process.exit(1);
}

servidor.listen(porta, host, () => {
    console.info(`gateway WhatsApp ouvindo em ${host}:${porta}`);
});

conexao.iniciar().catch(err => {
    console.error(`nao foi possivel iniciar o WhatsApp: ${err.message}`);
    process.exit(1);
});

async function sair(sinal) {
    console.info(`${sinal} recebido: encerrando`);
    servidor.close();
    await conexao.encerrar();
    process.exit(0);
}

process.on('SIGINT', () => sair('SIGINT'));
process.on('SIGTERM', () => sair('SIGTERM'));

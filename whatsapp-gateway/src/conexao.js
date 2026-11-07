'use strict';



const fs = require('node:fs');
const path = require('node:path');
const pino = require('pino');
const QRCode = require('qrcode');
const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion,
    Browsers,
} = require('@whiskeysockets/baileys');

const MAX_TENTATIVAS = 5;

function criarConexao({ authDir, logger = console, nivelLogBaileys = 'silent' }) {
    let sockAtual = null;
    let conectado = null;
    let estado = 'iniciando';
    let numero = '';
    let tentativas = 0;
    let timeoutsSeguidos = 0;
    let versao = null;
    let encerrando = false;
    let reconexao = null;

    const loggerBaileys = pino({ level: nivelLogBaileys });

    function limparSessao() {
        if (!fs.existsSync(authDir)) {
            return;
        }

        for (const item of fs.readdirSync(authDir)) {
            fs.rmSync(path.join(authDir, item), { recursive: true, force: true });
        }
    }

    async function obterVersao() {
        if (versao) {
            return versao;
        }
        try {
            ({ version: versao } = await fetchLatestBaileysVersion());
        } catch {
            versao = [2, 3000, 1035194821];
        }
        return versao;
    }

    function reconectar(esperaMs) {
        if (encerrando || reconexao !== null) {
            return;
        }
        reconexao = setTimeout(async () => {
            reconexao = null;
            try {
                await iniciar();
            } catch (err) {
                logger.error(`erro ao reconectar: ${err.message}`);
                estado = 'erro';
                reconectar(10_000);
            }
        }, esperaMs);
    }

    async function mostrarQr(qr) {
        estado = 'aguardando_qr';
        try {
            const desenho = await QRCode.toString(qr, { type: 'terminal', small: true });
            logger.info(`\nEscaneie o QR code com o WhatsApp do numero que envia os alertas:\n${desenho}`);
        } catch (err) {
            logger.error(`nao foi possivel desenhar o QR code: ${err.message}`);
        }
    }

    async function iniciar() {
        if (encerrando) {
            return;
        }
        estado = 'iniciando';
        fs.mkdirSync(authDir, { recursive: true });
        const { state, saveCreds } = await useMultiFileAuthState(authDir);

        const sock = makeWASocket({
            version: await obterVersao(),
            auth: state,
            logger: loggerBaileys,
            printQRInTerminal: false,
            browser: Browsers.macOS('Chrome'),
            syncFullHistory: false,
            markOnlineOnConnect: false,
            generateHighQualityLinkPreview: false,
            getMessage: async () => undefined,
            connectTimeoutMs: 60_000,
            keepAliveIntervalMs: 20_000,
            retryRequestDelayMs: 500,
            maxMsgRetryCount: 2,
        });
        sockAtual = sock;

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
            if (qr) {
                tentativas = 0;
                await mostrarQr(qr);
            }

            if (connection === 'open') {
                tentativas = 0;
                timeoutsSeguidos = 0;
                numero = sock.user?.id?.split(':')[0]?.split('@')[0] || '';
                conectado = sock;
                estado = 'conectado';
                logger.info(`WhatsApp conectado (numero final ...${numero.slice(-4)})`);
                return;
            }

            if (connection !== 'close') {
                return;
            }
            if (sock === sockAtual) {
                conectado = null;
            }
            const codigo = lastDisconnect?.error?.output?.statusCode;
            const mensagem = lastDisconnect?.error?.message || '';
            if (codigo === DisconnectReason.restartRequired && !encerrando) {

                logger.info('QR lido; reconectando para concluir o pareamento');
                reconectar(500);
                return;
            }
            logger.warn(`conexao fechada (codigo ${codigo ?? '-'}: ${mensagem || 'sem motivo'})`);

            if (encerrando || codigo === undefined) {
                estado = 'desconectado';
                return;
            }
            if (mensagem.includes('QR refs attempts ended')) {

                estado = 'aguardando_qr';
                reconectar(1500);
                return;
            }
            if (codigo === DisconnectReason.loggedOut || codigo === 401) {
                logger.warn('sessao encerrada pelo celular: apagando credenciais e gerando QR novo');
                estado = 'aguardando_qr';
                numero = '';
                tentativas = 0;
                limparSessao();
                reconectar(2000);
                return;
            }
            estado = 'erro';
            if (codigo === 440) {

                tentativas++;
                if (tentativas > MAX_TENTATIVAS) {
                    logger.error('sessao substituida varias vezes: ha outro gateway rodando com a mesma sessao?');
                    return;
                }
                reconectar(Math.min(15_000 * tentativas, 60_000));
                return;
            }
            if (mensagem.includes('Timed Out') || mensagem.includes('init queries')) {
                timeoutsSeguidos++;
                reconectar(Math.min(15_000 * timeoutsSeguidos, 120_000));
                return;
            }
            timeoutsSeguidos = 0;
            tentativas++;
            if (tentativas > MAX_TENTATIVAS) {

                logger.error(`${MAX_TENTATIVAS} reconexoes falharam; tentando de novo a cada 5 minutos`);
                reconectar(300_000);
                return;
            }
            reconectar(Math.min(3000 * tentativas, 30_000));
        });


    }

    async function encerrar() {
        encerrando = true;
        clearTimeout(reconexao);
        reconexao = null;
        try {
            sockAtual?.end(undefined);
        } catch (err) {
            logger.warn(`erro ao fechar a conexao: ${err.message}`);
        }
        sockAtual = null;
        conectado = null;
        estado = 'desconectado';
    }

    return {
        iniciar,
        encerrar,
        obterSock: () => conectado,
        obterEstado: () => ({ estado, numero }),
    };
}

module.exports = { criarConexao };

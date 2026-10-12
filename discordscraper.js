#!/usr/bin/env node

// Discord -> Immich media scraper bot.
//
// Reads config.json:
//   {
//     "token": "<discord bot token>",
//     "scan": [
//       {
//         "album": "<immich album name>",
//         "prefix": "<filename prefix>",
//         "channel": "<channel snowflake>"
//       }
//     ]
//   }
//
// For every scan target it looks at the newest MESSAGE_LIMIT messages of the
// channel and hands the attachments to discordscraper.py over stdin, as one
// newline delimited JSON array per target:
//
//   [{ "album": "...", "url": "...", "name": "<prefix><attachment name>",
//      "originalName": "<attachment name>",
//      "createdAt": <message timestamp in ms> }, ...]
//
// The python scanner then uploads anything Immich doesn't already have.
//
// This bot runs once: it scans every target, hands the work to the scanner and
// exits once the scanner is done.
//
// Pass --full to walk the entire channel history (back to channel creation)
// instead of just the newest MESSAGE_LIMIT messages. In that mode the scanner
// keeps going after finding duplicates instead of stopping at the first one.

import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { ActivityType, Client, Events, GatewayIntentBits } from "discord.js";

const CONFIG_PATH = path.join(import.meta.dirname, "config.json");
const SCANNER_PATH = path.join(import.meta.dirname, "discordscraper.py");
const PYTHON = path.join(import.meta.dirname, ".venv", "bin", "python3");

// How many messages to fetch per request while scanning.
const MESSAGE_LIMIT = 100;

// Walk the whole channel history and don't stop at duplicates.
const FULL = process.argv.includes("--full");

const SCANNING_STATUS = "Scanning media!";
const SLEEPING_STATUS = "Sleeping...";

const config = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

// Worker scanner, kept alive for the duration of the run.
const scanner = spawn(PYTHON, [SCANNER_PATH, ...(FULL ? ["--full"] : [])], {
  cwd: import.meta.dirname,
  stdio: ["pipe", "inherit", "inherit"],
});

scanner.on("error", (error) => {
  console.error(`Scanner failed to start: ${error.message}`);
  process.exitCode = 1;
});

scanner.on("exit", (code, signal) => {
  if (code === 0) {
    console.log("Scanner finished");
    return;
  }
  console.error(`Scanner exited (code=${code}, signal=${signal})`);
  process.exitCode = 1;
});

scanner.stdin.on("error", (error) => {
  console.error(`Scanner stdin error: ${error.message}`);
});

function setStatus(status, emoji) {
  client.user?.setActivity(`${status} ${emoji}`, { type: ActivityType.Watching });
}

async function scanTarget(target) {
  const channel = await client.channels.fetch(target.channel);
  const assets = [];
  let before;

  while (true) {
    const messages = await channel.messages.fetch(
      before ? { limit: MESSAGE_LIMIT, before } : { limit: MESSAGE_LIMIT },
    );
    if (messages.size === 0) {
      break;
    }

    // Newest first, so the scanner can stop as soon as it finds a known asset.
    const ordered = [...messages.values()].sort(
      (a, b) => b.createdTimestamp - a.createdTimestamp,
    );
    for (const message of ordered) {
      for (const attachment of message.attachments.values()) {
        assets.push({
          album: target.album,
          url: attachment.url,
          name: target.prefix + attachment.name,
          originalName: attachment.name,
          createdAt: message.createdTimestamp,
        });
      }
    }

    // Only page back to channel creation when --full is set.
    if (!FULL || messages.size < MESSAGE_LIMIT) {
      break;
    }
    before = ordered[ordered.length - 1].id;
  }

  return assets;
}

async function scan() {
  setStatus(SCANNING_STATUS, "👀");
  for (const target of config.scan ?? []) {
    const assets = await scanTarget(target);
    console.log(
      `Scanned ${assets.length} attachment(s) for album ${target.album}`,
    );
    if (assets.length === 0) {
      continue;
    }
    scanner.stdin.write(`${JSON.stringify(assets)}\n`);
  }
  setStatus(SLEEPING_STATUS, "😴");
}

// Close the scanner's input and wait for it to finish uploading.
async function waitForScanner() {
  if (scanner.exitCode !== null || scanner.signalCode !== null) {
    return;
  }
  const done = new Promise((resolve) => scanner.once("exit", resolve));
  scanner.stdin.end();
  await done;
}

client.once(Events.ClientReady, async (readyClient) => {
  console.log(`Logged in as ${readyClient.user.tag}`);
  try {
    await scan();
  } catch (error) {
    console.error("Scan failed:", error);
    process.exitCode = 1;
  }
  await waitForScanner();
  client.destroy();
});

client.login(config.token);

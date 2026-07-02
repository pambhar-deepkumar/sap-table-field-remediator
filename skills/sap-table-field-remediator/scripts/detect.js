#!/usr/bin/env node
/*
 * detect.js — deterministic ABAP DB-access detector (abaplint AST backbone).
 *
 * Emits ONE record per DB-access *statement* (not per textual mention) — plus field-level faults
 * (MATNR truncation on assignment, VBTYP literal compares) — so a file that names BSEG on 15 lines
 * yields findings only on the real access/fault lines, not TABLES/TYPES declarations.
 * Solves statement boundaries, multi-line SELECT, JOINs, IMPORT ... FROM DATABASE,
 * EXEC SQL ... ENDEXEC, and read-vs-write in one pass — things a regex gets wrong.
 *
 * It does NOT classify (no catalog lookup, no tier). It only reports WHAT was accessed,
 * HOW (read/write/cluster_read/native), and any dynamic/offset signals the catalog
 * step + LLM need. classify.py consumes this JSON.
 *
 * Usage:  node detect.js <dir-or-file> [<file> ...]   ->  JSON to stdout
 *   - directories are walked for *.abap only (paired *.prog.xml/*.clas.xml are metadata)
 *
 * Output: { "scanned_files": [...], "statements": [ {file,line,kind,access,objects,
 *           dynamic,dynamic_expr,offsets,snippet} ], "abaplint_version": "x" }
 */
"use strict";

const fs = require("fs");
const path = require("path");

let core;
try {
  core = require("@abaplint/core");
} catch (e) {
  process.stderr.write(
    "FATAL: @abaplint/core not installed. Run `npm install` in this scripts/ dir " +
      "(see SKILL.md 'Setup'). Detector cannot run without it.\n"
  );
  process.exit(3);
}
const { Registry, MemoryFile, Expressions } = core;

// --- statement classes we care about -------------------------------------- //
const READ = new Set(["Select", "SelectLoop"]);
const WRITE = new Set([
  "InsertDatabase",
  "UpdateDatabase",
  "ModifyDatabase",
  "DeleteDatabase",
]);

function listAbapFiles(target) {
  const out = [];
  const st = fs.statSync(target);
  if (st.isFile()) {
    if (target.endsWith(".abap")) out.push(target);
    return out;
  }
  for (const entry of fs.readdirSync(target)) {
    const full = path.join(target, entry);
    const s = fs.statSync(full);
    if (s.isDirectory()) out.push(...listAbapFiles(full));
    else if (entry.endsWith(".abap")) out.push(full);
  }
  return out;
}

function snippet(stmt) {
  return stmt.concatTokens().replace(/\s+/g, " ").slice(0, 160);
}

// Pull the cluster/area name out of  IMPORT ... FROM DATABASE <area>(<id>) ...
function importDatabaseArea(stmt) {
  const toks = stmt.getTokens();
  for (let i = 0; i < toks.length - 1; i++) {
    if (toks[i].getStr().toUpperCase() === "DATABASE") {
      return toks[i + 1].getStr();
    }
  }
  return null; // IMPORT from a non-DATABASE source (memory/dataset) — not our concern
}

// offset/length access (e.g. gv_matnr+9(9)) on field chains within a statement.
function offsetAccesses(stmt) {
  const offs = stmt.findAllExpressions(Expressions.FieldOffset);
  if (offs.length === 0) return [];
  // Pair each offset with the field chain it sits on + the surrounding statement kind.
  const chains = stmt
    .findAllExpressions(Expressions.FieldChain)
    .concat(stmt.findAllExpressions(Expressions.SimpleFieldChain));
  const out = [];
  for (const off of offs) {
    // the base identifier is the first token of the enclosing field chain;
    // fall back to scanning tokens before the '+'.
    let base = null;
    const offTok = off.getFirstToken();
    const toks = stmt.getTokens();
    const idx = toks.findIndex((t) => t === offTok);
    if (idx > 0) base = toks[idx - 1].getStr();
    out.push({ base, offset: off.concatTokens() });
  }
  return out;
}

function dbTables(stmt) {
  return stmt
    .findAllExpressions(Expressions.DatabaseTable)
    .map((e) => e.concatTokens().trim());
}

function isDynamic(name) {
  // dynamic target: (lv_tabname) or contains parens
  return /^\(.*\)$/.test(name) || name.includes("(");
}

function main() {
  const targets = process.argv.slice(2);
  if (targets.length === 0) {
    process.stderr.write("usage: node detect.js <dir-or-file> [...]\n");
    process.exit(2);
  }
  const files = [];
  for (const t of targets) files.push(...listAbapFiles(t));
  files.sort();

  const reg = new Registry();
  const relById = [];
  for (const f of files) {
    const code = fs.readFileSync(f, "utf8");
    reg.addFile(new MemoryFile(f, code));
    relById.push(f);
  }
  reg.parse();

  const statements = [];
  for (const f of files) {
    statements.push(...analyzeFileByName(reg, f));
  }

  process.stdout.write(
    JSON.stringify(
      {
        abaplint_version: core.Version ? core.Version.version : "unknown",
        scanned_files: files,
        statements,
      },
      null,
      2
    ) + "\n"
  );
}

// resolve the ABAPFile for an exact filename, then analyze.
function analyzeFileByName(reg, filename) {
  for (const obj of reg.getObjects()) {
    if (!obj.getABAPFiles) continue;
    for (const f of obj.getABAPFiles()) {
      if (f.getFilename() === filename) {
        return analyzeAbapFile(f, filename);
      }
    }
  }
  return [];
}

// the real per-file walk (decoupled from registry lookup).
function analyzeAbapFile(abapFile, relpath) {
  const stmts = [];
  const all = abapFile.getStatements();
  let inExec = false;
  let execStart = null;
  let execTokens = [];

  for (const s of all) {
    const type = s.get().constructor.name;
    const row = s.getFirstToken().getStart().getRow();

    if (type === "ExecSQL") {
      inExec = true;
      execStart = row;
      execTokens = [];
      continue;
    }
    if (inExec) {
      if (type === "EndExec") {
        inExec = false;
        const upper = execTokens.map((t) => t.toUpperCase());
        const fromIdx = upper.indexOf("FROM");
        const table = fromIdx >= 0 ? execTokens[fromIdx + 1] : null;
        const verb = upper[0] || "SELECT";
        const access = verb === "SELECT" ? "native_read" : "native_write";
        stmts.push({
          file: relpath,
          line: execStart,
          kind: "exec_sql",
          access,
          objects: table ? [table.replace(/[.,()]/g, "")] : [],
          dynamic: false,
          dynamic_expr: null,
          offsets: [],
          smell: "exec_sql_native",
          snippet: "EXEC SQL ... " + execTokens.slice(0, 12).join(" "),
        });
      } else {
        for (const t of s.getTokens()) execTokens.push(t.getStr());
      }
      continue;
    }

    if (READ.has(type) || WRITE.has(type)) {
      const tables = dbTables(s);
      const access = READ.has(type) ? "read" : "write";
      for (const tbl of tables) {
        stmts.push({
          file: relpath,
          line: row,
          kind: "open_sql",
          access,
          objects: [tbl],
          dynamic: isDynamic(tbl),
          dynamic_expr: isDynamic(tbl) ? tbl : null,
          offsets: [],
          snippet: snippet(s),
        });
      }
      continue;
    }

    if (type === "Import") {
      const area = importDatabaseArea(s);
      if (area) {
        stmts.push({
          file: relpath,
          line: row,
          kind: "cluster_import",
          access: "cluster_read",
          objects: [area],
          dynamic: isDynamic(area),
          dynamic_expr: isDynamic(area) ? area : null,
          offsets: [],
          snippet: snippet(s),
        });
      }
      continue;
    }

    const offs = offsetAccesses(s);
    if (offs.length) {
      stmts.push({
        file: relpath,
        line: row,
        kind: "offset_access",
        access: type === "Move" ? "slice_assign" : "slice_read",
        objects: [],
        dynamic: false,
        dynamic_expr: null,
        offsets: offs,
        statement_type: type,
        snippet: snippet(s),
      });
      continue;
    }

    // --- field-level faults on NON-DB statements (length/value-changed fields) --- //
    // These carry no DB object; classify.py resolves whether the referenced field is a
    // catalogued `status: CHANGED` field (only then is it a finding) — that keeps precision.

    // (a) assignment that may TRUNCATE a length-changed field into a shorter target
    //     e.g. MOVE gs_mseg-matnr TO lv_matnr, where lv_matnr is CHAR18 (MATNR is now 40).
    if (type === "Move") {
      const tgt = s.findFirstExpression(Expressions.Target);
      const src = s.findFirstExpression(Expressions.Source);
      if (tgt && src) {
        stmts.push({
          file: relpath,
          line: row,
          kind: "field_assign",
          access: "assign",
          objects: [],
          dynamic: false,
          dynamic_expr: null,
          offsets: [],
          source_expr: src.concatTokens().trim(),
          target_expr: tgt.concatTokens().trim(),
          snippet: snippet(s),
        });
      }
      continue;
    }

    // (b) literal comparison against a value-WIDENED field
    //     e.g. IF vbtyp = 'C', where VBTYP widened CHAR1 -> CHAR4 (single-char literals break).
    if (type === "If" || type === "ElseIf") {
      const hasCharLiteral = s.getTokens().some((t) => /^'[^']*'$/.test(t.getStr()));
      if (hasCharLiteral) {
        const fields = s
          .findAllExpressions(Expressions.FieldChain)
          .concat(s.findAllExpressions(Expressions.SimpleFieldChain))
          .map((e) => e.concatTokens().trim());
        const literals = s
          .getTokens()
          .map((t) => t.getStr())
          .filter((x) => /^'[^']*'$/.test(x));
        if (fields.length) {
          stmts.push({
            file: relpath,
            line: row,
            kind: "literal_compare",
            access: "compare",
            objects: [],
            dynamic: false,
            dynamic_expr: null,
            offsets: [],
            fields,
            literals,
            snippet: snippet(s),
          });
        }
      }
      continue;
    }
  }
  return stmts;
}

main();

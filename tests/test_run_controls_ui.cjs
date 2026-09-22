// Control requests must survive rapid clicks and unrelated pending saves.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../apps/dashboard/app.js'), 'utf8');
function context(fetch) {
  const messages = [];
  const c = vm.createContext({fetch, state:{token:'fixture'}, mutating:true,
    AbortController, setTimeout, clearTimeout, refresh:async()=>{}, toast:m=>messages.push(m)});
  vm.runInContext(source.slice(source.indexOf('async function api('), source.indexOf('async function mutate(')),c);
  return {c,messages};
}
const response = {ok:true,json:async()=>({})};

test('rapid pause then stop is serialized; stop is not dropped during another mutation', async()=>{
  const calls=[];let release;
  const {c}=context(url=>{
    calls.push(url);
    return calls.length===1 ? new Promise(resolve=>{release=()=>resolve(response);}) : Promise.resolve(response);
  });
  const pause=c.controlRun('run-1','pause','paused');
  const stop=c.controlRun('run-1','stop','stopped');
  const duplicate=c.controlRun('run-1','stop','stopped');
  assert.equal(stop,duplicate);
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(calls,['/api/runs/run-1/pause']);
  release();await Promise.all([pause,stop]);
  assert.deepEqual(calls,['/api/runs/run-1/pause','/api/runs/run-1/stop']);
});

test('failed pause does not discard the subsequent stop or target another run', async()=>{
  const calls=[];
  const {c,messages}=context(async url=>{
    calls.push(url);
    if(calls.length===1)throw Error('fixture connection failure');
    return response;
  });
  await Promise.all([c.controlRun('old-run','pause','paused'),c.controlRun('old-run','stop','stopped')]);
  assert.deepEqual(calls,['/api/runs/old-run/pause','/api/runs/old-run/stop']);
  assert.match(messages[0],/connection failure/);
  assert.equal(messages.at(-1),'stopped');
});

test('a missing control response times out without automatically resending', async()=>{
  let calls=0;
  const {c}=context((url,{signal})=>{
    calls++;
    return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>{
      const e=Error('aborted');e.name='AbortError';reject(e);
    }));
  });
  await assert.rejects(c.api('/api/runs/run-1/stop',{},5),/응답을 확인하지 못했습니다/);
  assert.equal(calls,1);
});

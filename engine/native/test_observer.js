const fs=require('fs');
const vm=require('vm');
const assert=require('assert');
const scope={};
vm.createContext(scope);
const file=__dirname+'/observer.js';
assert.ok(fs.existsSync(file),'native Observer code is not implemented');
vm.runInContext(fs.readFileSync(file,'utf8'),scope);
const cases=JSON.parse(fs.readFileSync(__dirname+'/observer-fixtures.json','utf8'));
for(const item of cases){
  const prepared=JSON.parse(JSON.stringify(scope.prepare(item.context)));
  assert.deepStrictEqual(prepared,item.prepared,item.name+' preparation parity');
  const checked=JSON.parse(JSON.stringify(scope.validateCandidate(item.context,item.value)));
  assert.deepStrictEqual(checked,item.expected,item.name+' validation parity');
}
console.log(cases.length+' native Observer contract fixtures passed');

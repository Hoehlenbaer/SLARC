const {chromium}=require('playwright'); const fs=require('fs');
(async()=>{const b=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const p=await b.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1});
p.on('pageerror',e=>console.log('err',e.message));
await p.goto('http://127.0.0.1:8765/index.html?'+(process.argv[3]||''));
await p.waitForFunction('window.DONE===true',{timeout:900000,polling:2000});
const d=await p.evaluate(()=>document.querySelector('canvas').toDataURL('image/png'));
fs.writeFileSync(process.argv[2],Buffer.from(d.split(',')[1],'base64')); await b.close();})();

// Run Next's standalone build with its browser assets in place.
import {cpSync,existsSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=dirname(dirname(fileURLToPath(import.meta.url)));
let hostname='127.0.0.1',port=process.env.PORT||'3000';
for(let index=2;index<process.argv.length;index++){
 const flag=process.argv[index],value=process.argv[++index];
 if(!value||!['--hostname','--port'].includes(flag))throw new Error('Use --hostname ADDRESS and --port NUMBER.');
 if(flag==='--hostname')hostname=value;else port=value;
}
if(!/^\d+$/.test(port)||Number(port)<1||Number(port)>65535)throw new Error('Choose a port from 1 to 65535.');
const output=join(root,'.next','standalone'),server=join(output,'server.js');
if(!existsSync(server))throw new Error('No production build found. Run npm run build first.');
cpSync(join(root,'.next','static'),join(output,'.next','static'),{recursive:true,force:true});
if(existsSync(join(root,'public')))cpSync(join(root,'public'),join(output,'public'),{recursive:true,force:true});
process.env.HOSTNAME=hostname;process.env.PORT=port;
await import(pathToFileURL(server).href);

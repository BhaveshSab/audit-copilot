/** Disposable real PostgreSQL-WASM+pgvector, Nest API, official MCP, Python app.
 * No production URL or credential is read. All database state is in memory.
 */
import {PGlite} from '@electric-sql/pglite';
import {btree_gist} from '@electric-sql/pglite/contrib/btree_gist';
import {vector} from '@electric-sql/pglite-pgvector';
import {PGLiteSocketServer} from '@electric-sql/pglite-socket';
import {createRequire} from 'node:module';
import {readFileSync,readdirSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomBytes} from 'node:crypto';
import {spawn} from 'node:child_process';
const serviceRoot=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const root=process.env.ASSETFLOW_ROOT || (existsSync(resolve(serviceRoot,'../backend')) ? resolve(serviceRoot,'..') : resolve(serviceRoot,'../assetflow'));
const require=createRequire(resolve(root,'backend/package.json'));
const db=await PGlite.create({extensions:{btree_gist,vector}});
const server=new PGLiteSocketServer({db,host:'127.0.0.1',port:0,maxConnections:20});
let app;
try{
 for(const folder of readdirSync(resolve(root,'backend/prisma/migrations')).sort()){
  const p=resolve(root,'backend/prisma/migrations',folder,'migration.sql');
  if(existsSync(p))await db.exec(readFileSync(p,'utf8'));
 }
 await db.exec(readFileSync(resolve(root,'audit-copilot/schema.sql'),'utf8'));
 await server.start();
 const dsn=`postgresql://postgres:postgres@${server.getServerConn()}/postgres`;
 Object.assign(process.env,{NODE_ENV:'test',DATABASE_URL:dsn,JWT_SECRET:randomBytes(32).toString('hex'),BCRYPT_ROUNDS:'4',AUTH_THROTTLE_LIMIT:'1000',THROTTLE_LIMIT:'100000',REDIS_URL:'',MAIL_TRANSPORT:'dev',BOOTSTRAP_ADMIN_EMAIL:'',GOOGLE_CLIENT_ID:'',OTEL_SDK_DISABLED:'true'});
 const {NestFactory}=require('@nestjs/core');
 const {AppModule}=require(resolve(root,'backend/dist/app.module.js'));
 const {configureApp}=require(resolve(root,'backend/dist/configure-app.js'));
 app=await NestFactory.create(AppModule,{logger:false});configureApp(app);await app.listen(0,'127.0.0.1');
 const base=`http://127.0.0.1:${app.getHttpServer().address().port}/api`;
 const password=randomBytes(24).toString('hex');
 async function call(path,body,token){const r=await fetch(base+path,{method:body?'POST':'GET',headers:{...(token?{Authorization:`Bearer ${token}`} : {}),'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});const x=await r.json();if(!r.ok)throw Error(`Fixture setup failed (${r.status})`);return x;}
 await call('/auth/signup',{name:'Integration reviewer',email:'integration@demo.invalid',password});
 // Promotion only in disposable test DB, never an admin signup parameter.
 await db.query(`UPDATE "User" SET role='ADMIN' WHERE email=$1`,['integration@demo.invalid']);
 const {token}=await call('/auth/login',{email:'integration@demo.invalid',password});
 const {PrismaService}=require(resolve(root,'backend/dist/prisma/prisma.service.js'));
 const prisma=app.get(PrismaService);
 const category=await prisma.assetCategory.create({data:{name:'Test equipment'}});
 await prisma.asset.create({data:{name:'Test laptop',assetTag:'AF-TEST-001',categoryId:category.id}});
 const cycle=await call('/audits',{name:'Isolated integration',startDate:new Date().toISOString(),endDate:new Date(Date.now()+86400000).toISOString()},token);
 const items=await call(`/audits/${cycle.id}/items`,null,token);
 const env={...process.env,ASSETFLOW_URL:base,ASSETFLOW_TOKEN:token,COPILOT_MODE:'live',COPILOT_DATABASE_URL:dsn,TEST_CYCLE:cycle.id,TEST_ITEM:items.items[0].id};
 const exit=await new Promise((done,reject)=>{
  const p=spawn(process.env.COPILOT_PYTHON||resolve(root,'.venv/bin/python'),['-m','audit_copilot.integration_probe'],{cwd:serviceRoot,env,stdio:['ignore','inherit','inherit']});
  const timer=setTimeout(()=>p.kill('SIGTERM'),90000);
  p.once('error',reject);p.once('exit',c=>{clearTimeout(timer);done(c);});
 });
 if(exit!==0)throw Error('Python integration probe failed');
 const decisions=await prisma.copilotDecision.count();
 const activity=await prisma.activityLog.count({where:{action:'audit.copilot_decision_applied'}});
 if(decisions!==1||activity!==1)throw Error('Expected exactly one decision and activity event');
 console.log('PASS: real AssetFlow API + official MCP stdio + PostgreSQL FTS/pgvector + review/idempotent retry. LLM output is FIXTURE, not live.');
}finally{if(app)await app.close();await server.stop();await db.close();}

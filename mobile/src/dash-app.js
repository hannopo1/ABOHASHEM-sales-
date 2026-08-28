/* Abu Hashem mobile — module extracted verbatim from the standalone build.
   The App component (9 sections, filters, sheets) and the React bootstrap.
   Do not reformat: this is byte-identical to the shipped runtime so the
   rebuilt file can be diffed against it. Regenerate the bundle with
   `python3 mobile/build_standalone.py`. */
class App extends React.Component {
  state = { ready:false, err:null, T:null, api:null,
    section:"overview", sheet:null,
    filters:{month:"",customer:"",rep:"",brand:"",item:"",status:"",aging:""},
    /* Filters for the DASH_DATA path — separate from the window.DASH filter
       set above, which slices a transactional schema this dataset lacks. */
    rf:{rep:null,brand:null,customerCode:null,itemName:null}, rfOpts:null,
    /* Two independent extracts ship together; they cover different periods and
       customer counts, so they are switched between rather than merged. */
    src:"dash", AG:null, C:null, fq:"", loadMsg:null, barHidden:true,
    snaps:[], snap:null, cmp:null, stmt:null, ins:{} };
  /* The bar is nine fields tall — open by default it pushes every chart off
     a phone screen, so it starts collapsed behind the header button. */

  componentDidMount(){
    /* Handle for the export tests in mobile/tools/, which drive the real page
       rather than a mock so the shipped bundle is what gets verified. */
    window.__app = this;
    try{
      const AG = G, C = window.__C;
      /* Several AR snapshots ship as inert JSON blocks; only the selected one is
         parsed. Newest as_of wins, most recently generated breaking the tie. */
      const snaps = this.readSnapshots();
      let D = this.storedDash(), snap = null;
      if(!D && snaps.length){
        snaps.sort((a,b)=>a.as_of===b.as_of ? (a.generated<b.generated?1:-1) : (a.as_of<b.as_of?1:-1));
        snap = snaps[0].key;
        D = this.parseSnapshot(snaps[0]);
      }
      if(!D) D = window.DASH || null;
      const api = D ? A.makeApi(D) : null;
      const f = {...this.state.filters};
      if(api) f.month = D.meta.default_month || "";
      /* Both extracts stay reachable — the app switches rather than letting one
         hide the other. */
      const RD = window.DASH_DATA || null;
      const R2 = RD ? R : null;
      const rfOpts = (R2&&RD) ? R2.filterOptions(RD) : null;
      this.setState({ready:true, T, A, AG, C, api, filters:f, R:R2, RD, rfOpts,
                     snaps, snap,
                     src: api ? "dash" : "repo",
                     section: api ? this.state.section : (RD?"fin":this.state.section)});
    }catch(e){ this.setState({ready:true, err:String(e)}); }
  }

  /* A newer build.py export can be loaded at runtime; it never leaves the
     device. Validated before it is allowed to replace the bundled payload. */
  /* Snapshots are embedded as inert <script type="application/json"> blocks and
     parsed on demand -- measured ~18 ms each with JSON.parse against ~67 ms to
     evaluate the same payload as a JS object literal, so the browser never pays
     for a snapshot nobody opened. */
  readSnapshots(){
    const out = [];
    const idx = document.getElementById("snap-index");
    if(!idx) return out;
    try{
      for(const e of JSON.parse(idx.textContent)){
        if(document.getElementById("snap-"+e.file)) out.push({...e, key:e.file, data:null});
      }
    }catch(err){}
    return out;
  }
  parseSnapshot(sn){
    if(sn.data) return sn.data;
    const el = document.getElementById("snap-"+sn.file);
    if(!el) return null;
    /* The build escapes "<" + "/" inside the payload so a closing script tag
       occurring in customer data cannot terminate the block early; undo it. */
    sn.data = JSON.parse(el.textContent.split("<\\/").join("</"));
    return sn.data;
  }
  pickSnapshot(key){
    const st = this.state;
    const sn = (st.snaps||[]).find(x=>x.key===key);
    if(!sn) return;
    let D; try{ D = this.parseSnapshot(sn); }
    catch(e){ this.setState({loadMsg:"تعذّر قراءة اللقطة: "+e.message}); return; }
    this._optKey = null;                       // option lists are per-payload
    this.setState({api:st.A.makeApi(D), snap:key, src:"dash", sheet:null, stmt:null,
      filters:{...st.filters, month:D.meta.default_month||"all"},
      cmp:(st.cmp===key)?null:st.cmp});
  }
  pickCompare(key){
    const sn = (this.state.snaps||[]).find(x=>x.key===key);
    if(sn && !sn.data){ try{ this.parseSnapshot(sn); }catch(e){} }
    this.setState({cmp:key});
  }

  storedDash(){
    try{
      const raw = window.localStorage && localStorage.getItem("abh_dash");
      if(!raw) return null;
      const D = JSON.parse(raw);
      return this.validDash(D) ? D : null;
    }catch(e){ return null; }
  }
  validDash(D){
    return !!(D && D.meta && D.meta.as_of && Array.isArray(D.invoices)
              && Array.isArray(D.lines) && D.receivables && Array.isArray(D.receivables.rows));
  }
  loadDashFile(file){
    const rd = new FileReader();
    rd.onload = () => {
      try{
        const txt = String(rd.result);
        const i = txt.indexOf("{");
        const j = txt.lastIndexOf("}");
        if(i < 0 || j <= i) throw new Error("لا يحتوي الملف على كائن JSON");
        const D = JSON.parse(txt.slice(i, j+1));
        if(!this.validDash(D)) throw new Error("المخطط غير مطابق لـ window.DASH");
        try{ localStorage.setItem("abh_dash", JSON.stringify(D)); }catch(e){}
        const api = this.state.A.makeApi(D);
        this.setState({api, src:"dash", sheet:null,
          filters:{...this.state.filters, month:D.meta.default_month||""},
          loadMsg:"تم تحميل "+(D.meta.period_label||"الملف")+" — لقطة "+D.meta.as_of});
      }catch(e){ this.setState({loadMsg:"تعذّر التحميل: "+e.message}); }
    };
    rd.readAsText(file);
  }

  set(k,v){ this.setState(s=>({filters:{...s.filters,[k]:v}, sheet:null})); }
  E(t,s,c){ return React.createElement(t,{style:s},c); }

  card(title,children,opt){
    const o=opt||{};
    return React.createElement("div",{key:o.k||title,style:{background:"rgba(17,24,39,.85)",border:"1px solid rgba(255,255,255,.08)",borderRadius:16,padding:"13px 13px 11px",display:"flex",flexDirection:"column",gap:9}},
      React.createElement("div",{style:{display:"flex",alignItems:"baseline",gap:7,flexWrap:"wrap"}},
        React.createElement("h3",{style:{margin:0,fontSize:13.5,fontWeight:700,color:"#e2e8f0"}},title),
        o.approx?React.createElement("span",{style:{fontSize:9.5,padding:"2px 6px",borderRadius:6,background:"rgba(245,158,11,.14)",color:"#f59e0b"}},"تقديري"):null,
        o.sub?React.createElement("span",{style:{fontSize:10.5,color:"#64748b",marginInlineStart:"auto"}},o.sub):null),
      children);
  }
  empty(msg){ return React.createElement("div",{style:{padding:"20px 12px",textAlign:"center",fontSize:12,color:"#64748b",border:"1px dashed rgba(255,255,255,.10)",borderRadius:12}},msg); }
  skel(h){ return React.createElement("div",{style:{height:h||64,borderRadius:12,background:"linear-gradient(90deg,rgba(255,255,255,.03),rgba(255,255,255,.07),rgba(255,255,255,.03))",backgroundSize:"200% 100%",animation:"shim 1.4s linear infinite"}}); }

  rowsList(rows,cols,onPick){
    if(!rows.length) return this.empty("لا توجد بيانات");
    return React.createElement("div",{style:{display:"flex",flexDirection:"column",gap:7}},
      rows.map((r,i)=>React.createElement("div",{key:i,onClick:()=>onPick?onPick(r):this.setState({sheet:{cols,r}}),style:{padding:"10px 11px",borderRadius:12,background:"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.06)",display:"flex",flexDirection:"column",gap:5,cursor:"pointer"}},
        cols.slice(0,4).map((c,j)=>React.createElement("div",{key:j,style:{display:"flex",justifyContent:"space-between",gap:10,fontSize:j===0?13:11.5}},
          React.createElement("span",{style:{color:"#64748b"}},c[0]),
          React.createElement("b",{style:{color:j===0?"#e2e8f0":"#cbd5e1",fontWeight:j===0?700:600,fontFamily:j===0?"inherit":"'JetBrains Mono',monospace"}},String(c[1](r)??"—")))))));
  }

  lineChart(pts,color){
    if(!pts.length) return this.empty("لا توجد بيانات");
    const w=300,h=92,mx=Math.max(...pts.map(p=>p.v),1);
    const X=i=>pts.length<2?w:i*(w/(pts.length-1)), Y=v=>h-(v/mx)*(h-8);
    const d=pts.map((p,i)=>X(i).toFixed(1)+","+Y(p.v).toFixed(1)).join(" ");
    return React.createElement("svg",{viewBox:"0 0 "+w+" "+h,style:{width:"100%",height:100,display:"block"}},
      React.createElement("polygon",{points:d+" "+w+","+h+" 0,"+h,fill:color,opacity:.2}),
      React.createElement("polyline",{points:d,fill:"none",stroke:color,strokeWidth:2.4,strokeLinecap:"round"}));
  }
  barsH(rows,fmt){
    const rs=rows.filter(r=>r[1]!=null);
    if(!rs.length) return this.empty("لا توجد بيانات");
    const mx=Math.max(...rs.map(r=>r[1]),1);
    return React.createElement("div",{style:{display:"flex",flexDirection:"column",gap:7}},
      rs.map((r,i)=>React.createElement("div",{key:i,style:{display:"flex",alignItems:"center",gap:8}},
        React.createElement("span",{style:{width:92,flex:"none",fontSize:10.5,color:"#94a3b8",overflow:"hidden",whiteSpace:"nowrap",textOverflow:"ellipsis"}},r[0]),
        React.createElement("span",{style:{flex:1,height:9,borderRadius:99,background:"rgba(255,255,255,.05)",overflow:"hidden",display:"block"}},
          React.createElement("span",{"data-bar":"fill",style:{display:"block",height:"100%",width:(r[1]/mx*100)+"%",borderRadius:99,background:r[2]||"#3b82f6"}})),
        React.createElement("span",{style:{fontSize:10.5,color:"#cbd5e1",flex:"none",fontFamily:"'JetBrains Mono',monospace"}},fmt(r[1])))));
  }
  gauge(rate,T,label){
    const p=Math.max(0,Math.min(1,rate||0));
    return React.createElement("div",{style:{display:"flex",alignItems:"center",gap:14}},
      React.createElement("div",{style:{position:"relative",width:84,height:84,flex:"none",borderRadius:"50%",background:"conic-gradient(#10b981 "+(p*360)+"deg, rgba(255,255,255,.06) 0)"}},
        React.createElement("div",{style:{position:"absolute",inset:9,borderRadius:"50%",background:"#0d1220",display:"grid",placeItems:"center",fontSize:15,fontWeight:800,color:"#e2e8f0",fontFamily:"'JetBrains Mono',monospace"}},T.pct(p))),
      React.createElement("div",{style:{fontSize:12,lineHeight:1.8,color:"#94a3b8"}},label));
  }

  /* Generic KPI grid for the window.DASH_DATA (repo-adapter) path: rows are
     [label,value,sub,color] tuples, same shape the repo's own tab_*.js cards
     build — no icon, since the source desktop cards carry none either. */
  kpiGridRepo(rows){
    return React.createElement("div",{key:"kpi",style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:7}},
      rows.map((d,i)=>React.createElement("div",{key:i,style:{padding:"11px 11px 9px",borderRadius:14,background:"rgba(17,24,39,.85)",border:"1px solid rgba(255,255,255,.08)",borderInlineStart:"3px solid "+(d[3]||"#3b82f6"),display:"flex",flexDirection:"column",gap:3}},
        React.createElement("span",{style:{fontSize:15,fontWeight:800,color:"#f1f5f9",fontFamily:"'JetBrains Mono',monospace"}},d[1]),
        React.createElement("span",{style:{fontSize:10.5,color:"#94a3b8",lineHeight:1.5}},d[0]),
        d[2]?React.createElement("span",{style:{fontSize:9.5,color:"#64748b"}},d[2]):null)));
  }

  /* Small multiples — same pattern the repo uses for per-brand / per-customer
     / per-item forecast grids (tab_forecast.js, tab_brand.js). */
  miniLines(entries){
    return React.createElement("div",{style:{display:"flex",gap:8,flexWrap:"wrap"}},
      entries.map((e,i)=>React.createElement("div",{key:i,style:{flex:"1 1 28%",minWidth:92,display:"flex",flexDirection:"column",gap:4}},
        React.createElement("span",{style:{fontSize:10,color:e[1],fontWeight:700,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}},e[0]),
        this.lineChart(e[2],e[1]))));
  }

  renderVals(){
    const st=this.state;
    if(!st.ready) return {bodyEl:[this.skel(80),this.skel(150),this.skel(120)], statusEl:"…"};
    if(st.err) return {bodyEl:this.empty("خطأ في التحميل: "+st.err), statusEl:"error"};
    if(st.api && st.src!=="repo") return this.build();
    if(st.RD && st.R) return this.buildRepo();
    if(st.api) return this.build();
    return this.noData();
  }

  /* No window.DASH: keep every label/section/KPI slot, show values unavailable. */
  noData(){
    const st=this.state, T=st.T, SEC=T.SECTION_LABELS;
    const cur=SEC.find(s=>s.id===st.section)||SEC[0];
    const NAV=[["overview","لوحة"],["sales","المبيعات"],["customers","العملاء"],["receivables","المديونية"]];
    const navEl=React.createElement("div",{style:{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:2}},
      NAV.map(([id,lab])=>{const on=st.section===id;
        return React.createElement("div",{key:id,onClick:()=>this.setState({section:id,sheet:null}),style:{display:"flex",flexDirection:"column",alignItems:"center",gap:4,padding:"6px 0",borderRadius:12,cursor:"pointer",background:on?"rgba(59,130,246,.12)":"transparent",color:on?"#93c5fd":"#64748b"}},
          React.createElement("span",{style:{width:19,height:19,display:"block"},dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round">'+T.KPI_ICONS[id==="overview"?"sales":id==="sales"?"money":id==="customers"?"users":"warn"]+'</svg>'}}),
          React.createElement("span",{style:{fontSize:9.5,fontWeight:on?700:400}},lab));})
      .concat([React.createElement("div",{key:"more",onClick:()=>this.setState({sheet:"nav"}),style:{display:"flex",flexDirection:"column",alignItems:"center",gap:4,padding:"6px 0",borderRadius:12,cursor:"pointer",color:"#64748b"}},
        React.createElement("span",{style:{fontSize:17,lineHeight:"19px"}},"⋯"),
        React.createElement("span",{style:{fontSize:9.5}},"المزيد"))]));
    const chipsEl=React.createElement("div",{style:{flex:"none",position:"relative",display:"flex",alignItems:"center",gap:6,padding:"8px 13px",overflowX:"auto",borderBottom:"1px solid rgba(255,255,255,.06)"}},
      React.createElement("span",{style:{fontSize:12,fontWeight:700,color:"#e2e8f0",flex:"none",whiteSpace:"nowrap"}},cur.h2),
      React.createElement("span",{style:{fontSize:10.5,padding:"4px 9px",borderRadius:99,background:"rgba(245,158,11,.14)",border:"1px solid rgba(245,158,11,.3)",color:"#fcd34d",flex:"none",whiteSpace:"nowrap",marginInlineStart:"auto"}},"غير متاح"));
    const kpis=React.createElement("div",{key:"k",style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:7}},
      T.KPI_DEFS.map((d,i)=>React.createElement("div",{key:i,style:{padding:"11px 11px 9px",borderRadius:14,background:"rgba(17,24,39,.85)",border:"1px solid rgba(255,255,255,.08)",borderInlineStart:"3px solid "+d.accent,display:"flex",flexDirection:"column",gap:3}},
        React.createElement("span",{style:{color:d.accent,display:"block",height:16},dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round">'+T.KPI_ICONS[d.icon]+'</svg>'}}),
        React.createElement("span",{style:{fontSize:14,fontWeight:800,color:"#64748b",fontFamily:"'JetBrains Mono',monospace"}},"غير متاح"),
        React.createElement("span",{style:{fontSize:10.5,color:"#94a3b8",lineHeight:1.5}},d.label))));
    const bodyEl=[
      React.createElement("div",{key:"p",style:{fontSize:11,color:"#64748b",lineHeight:1.7}},cur.p),
      React.createElement("div",{key:"w",style:{padding:"12px 13px",borderRadius:14,background:"rgba(245,158,11,.08)",border:"1px solid rgba(245,158,11,.24)",fontSize:12,lineHeight:1.85,color:"#fcd34d"}},"data.js لم يُحمّل — الملف المرفق لا يتضمّن حِزمة البيانات. البنية والمسميات والصيغ محفوظة كما هي، والقيم تظهر «غير متاحة» بدلًا من اختراعها. بمجرد توفّر window.DASH تُملأ كل الشاشات تلقائيًا."),
      kpis,
      this.card("اتجاه المبيعات الشهري",this.empty("لا توجد بيانات"),{k:"n1"}),
      this.card("أعمار الديون",this.empty("لا توجد بيانات"),{approx:true,k:"n2"})];
    const sectionListEl=React.createElement("div",{dir:"rtl",style:{display:"flex",flexWrap:"wrap",gap:6}},
      SEC.map(s=>React.createElement("span",{key:s.id,onClick:()=>this.setState({section:s.id}),style:{fontSize:11,padding:"5px 10px",borderRadius:99,cursor:"pointer",background:st.section===s.id?"rgba(59,130,246,.16)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.08)",color:"#cbd5e1"}},s.label)));
    let sheetEl=null;
    if(st.sheet==="nav") sheetEl=React.createElement("div",{onClick:()=>this.setState({sheet:null}),style:{position:"absolute",inset:0,zIndex:9,background:"rgba(3,6,14,.7)",display:"flex",alignItems:"flex-end"}},
      React.createElement("div",{onClick:e=>e.stopPropagation(),style:{width:"100%",maxHeight:"78%",overflow:"auto",background:"#111827",borderTop:"1px solid rgba(255,255,255,.10)",borderRadius:"22px 22px 0 0",padding:"14px 14px 26px",display:"flex",flexDirection:"column",gap:8}},
        SEC.map(s=>React.createElement("div",{key:s.id,onClick:()=>this.setState({section:s.id,sheet:null}),style:{padding:"12px 13px",borderRadius:12,background:st.section===s.id?"rgba(59,130,246,.12)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.07)",fontSize:13,color:"#e2e8f0",cursor:"pointer"}},s.label))));
    const statusEl=React.createElement("div",null,
      React.createElement("b",{style:{color:"#f59e0b"}},"window.DASH غير موجود"),
      React.createElement("div",{style:{marginTop:6,lineHeight:1.9}},"الملفان المرفقان يشملان الأنماط والمنطق والمسميات، لكن حِزمة data.js غير مضمّنة، فلا توجد قيم لعرضها. لا شيء مُختلق: كل خانة تُعلَن «غير متاحة» حتى يُحمّل المصدر."));
    const filterBtnEl=React.createElement("span",{style:{width:34,height:34,flex:"none",borderRadius:10,background:"rgba(255,255,255,.02)",border:"1px solid rgba(255,255,255,.06)",display:"grid",placeItems:"center",color:"#475569",opacity:.6},dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>'}});
    return {bodyEl, navEl, chipsEl, filterBarEl:null, srcEl:null, filterBtnEl,
            exportBtnEl:null, sheetEl, statusEl, sectionListEl};
  }

  /* One tile grid for every KPI surface. Rows are [label, value, sub, colour].
     This replaces the copies that had drifted apart across the sections. */
  kpiTiles(rows, k){
    return React.createElement("div",{key:k||"kpi",style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:7}},
      rows.map((d,i)=>React.createElement("div",{key:i,style:{padding:"11px 11px 9px",borderRadius:14,
          background:"rgba(17,24,39,.85)",border:"1px solid rgba(255,255,255,.08)",
          borderInlineStart:"3px solid "+(d[3]||"#3b82f6"),display:"flex",flexDirection:"column",gap:3}},
        React.createElement("span",{style:{fontSize:15,fontWeight:800,color:"#f1f5f9",
          fontFamily:"'JetBrains Mono',monospace"}},d[1]),
        React.createElement("span",{style:{fontSize:10.5,color:"#94a3b8",lineHeight:1.5}},d[0]),
        d[2]?React.createElement("span",{style:{fontSize:9.5,color:"#64748b"}},d[2]):null)));
  }

  /* ---- AR movement between two snapshots -----------------------------------
     Not a desktop view: the desktop loads one payload and cannot difference the
     ledger. With several snapshots shipped, this is the most actionable
     collections screen in the app -- who moved, and by how much, in a week. */
  arMoveBody(X,T,api){
    const st=this.state, C=st.C, snaps=st.snaps||[];
    const cur=snaps.find(s2=>s2.key===st.snap);
    const others=snaps.filter(s2=>s2.key!==st.snap);
    if(!others.length) return [this.card("حركة المديونية",this.empty("تحتاج لقطتين على الأقل للمقارنة"),{k:"m0"})];
    /* Two snapshots can share an as_of and differ only in their collections
       extract; comparing those shows a flat ledger and teaches nothing. Default
       to the nearest snapshot with a DIFFERENT ledger date. */
    const dated=others.filter(s2=>!cur || s2.as_of!==cur.as_of);
    const cmpKey=st.cmp||((dated[0]||others[0]).key);
    const from=snaps.find(s2=>s2.key===cmpKey), to=snaps.find(s2=>s2.key===st.snap);
    if(!from||!to) return [this.card("حركة المديونية",this.empty("لقطة غير معروفة"),{k:"m1"})];
    /* The default comparison was never picked by hand, so parse it here. */
    for(const sn of [from,to]) if(!sn.data){
      try{ this.parseSnapshot(sn); }
      catch(e){ return [this.card("حركة المديونية",
        this.empty("تعذّر قراءة اللقطة: "+e.message),{k:"m1"})]; }
    }
    /* Always read older -> newer so a rise is a rise regardless of pick order. */
    const a=from.as_of<=to.as_of?from:to, b=from.as_of<=to.as_of?to:from;
    const mv=C.arMovement(a.data,b.data);
    const sign=x=>(x>=0?"+":"")+T.egpK(x);
    const sameDay=a.as_of===b.as_of;

    const picker=React.createElement("div",{key:"pk",style:{display:"flex",flexDirection:"column",gap:6}},
      React.createElement("span",{style:{fontSize:10.5,color:"#64748b"}},"قارن اللقطة الحالية بـ"),
      React.createElement("select",{value:cmpKey,onChange:e=>this.pickCompare(e.target.value),
        style:{width:"100%",padding:"9px 10px",borderRadius:10,fontSize:12,fontFamily:"inherit",
          background:"rgba(255,255,255,.03)",border:"1px solid rgba(42,120,214,.45)",
          color:"#93c5fd",fontWeight:700,appearance:"none",WebkitAppearance:"none",boxSizing:"border-box"}},
        others.map(o=>React.createElement("option",{key:o.key,value:o.key,
          style:{background:"#111827",color:"#e2e8f0"}},o.label))));

    return [
      React.createElement("div",{key:"n",style:{padding:"11px 12px",borderRadius:12,
          background:"rgba(42,120,214,.09)",border:"1px solid rgba(42,120,214,.26)",
          fontSize:11,lineHeight:1.85,color:"#bfdbfe"}},
        sameDay
          ? ["اللقطتان المختارتان تحملان تاريخ المديونية نفسه (",
             this.dateEl(a.as_of,"a"),") ولا تختلفان إلا في مستخرَج التحصيلات، "
             +"لذلك لا توجد حركة في دفتر الأرصدة. اختر لقطة بتاريخ مختلف للمقارنة."]
          : ["يقارن هذا القسم رصيد كل عميل بين لقطتَي مديونية: ",
             this.dateEl(a.as_of,"a")," و ",this.dateEl(b.as_of,"b"),
             ". لوحة الحاسوب لا تستطيع ذلك لأنها تحمّل لقطة واحدة فقط. مجموع الفروق يطابق فرق الإجماليين بالضبط."]),
      picker,
      this.kpiTiles([
        ["صافي الحركة", sign(mv.netDelta), this.ltr(a.as_of)+" ← "+this.ltr(b.as_of), mv.netDelta>=0?"#ef4444":"#10b981"],
        ["الرصيد الآن", T.egpK(mv.totTo), "كان "+T.egpK(mv.totFrom), "#f59e0b"],
        ["ارتفع", T.fmtInt?T.fmtInt(mv.rose):String(mv.rose), sign(mv.dRose)+" · عميل", "#ef4444"],
        ["انخفض", String(mv.fell), sign(mv.dFell)+" · عميل", "#10b981"],
        ["عملاء جدد", String(mv.added), sign(mv.dAdded), "#f97316"],
        ["سُدِّد بالكامل", String(mv.cleared), sign(mv.dCleared), "#06b6d4"],
      ],"mk"),
      this.chartCard("أكبر 12 حركة", C.arMovementChart(mv),
        {k:"m2",sub:"أحمر = ارتفاع الدين · أخضر = سداد",
         onPick:(p,o)=>{ const c=o._codes&&o._codes[p.dataIndex]; if(c!=null) this.setState({stmt:c}); }}),
      this.card("حركة كل عميل",this.rowsList(mv.rows.filter(r=>r.kind!=="flat"),[
        ["العميل",r=>r.name],
        ["الفرق",r=>(r.delta>=0?"+":"")+T.num(r.delta)],
        ["قبل",r=>T.num(r.from)],
        ["بعد",r=>T.num(r.to)],
        ["الحالة",r=>({up:"ارتفع",down:"انخفض",new:"عميل جديد",cleared:"سُدِّد بالكامل"})[r.kind]||"—"],
        ["المندوب",r=>r.rep]],r=>this.setState({stmt:r.code})),
        {k:"m3",sub:mv.rows.filter(r=>r.kind!=="flat").length+" عميل تحرّك · اضغط لكشف الحساب"}),
      this.card("تدقيق",React.createElement("div",{style:{fontSize:11,lineHeight:1.9,color:"#94a3b8"}},
        "مجموع فروق العملاء − فرق الإجماليين = ",
        React.createElement("b",{style:{color:Math.abs(mv.reconDelta)<0.01?"#10b981":"#ef4444",
          fontFamily:"'JetBrains Mono',monospace"}},T.num(mv.reconDelta)),
        Math.abs(mv.reconDelta)<0.01?" — مطابق تمامًا.":" — غير مطابق، لا تعتمد الأرقام."),{k:"m4"})];
  }

  /* ---- chart card, insight panel, statement -------------------------------- */

  /* A card whose body is a chart. `pick` maps a click on a category chart back
     to a filter -- behaviour the desktop does not have, and the single biggest
     usability win on a phone: tapping a slice beats hunting a dropdown. */
  chartCard(title, option, opt){
    const o = opt || {};
    const C = this.state.C;
    if(!option || C.isEmpty(option))
      return this.card(title, this.empty(o.emptyMsg||"لا توجد بيانات"), o);
    const body = [
      React.createElement(EChart,{key:"c", option, h:o.h||C.H.base, onPick:o.onPick}),
      o.onPick?React.createElement("div",{key:"h",style:{fontSize:9.5,color:"#475569",textAlign:"center"}},
        "اضغط على أي عنصر للتصفية"):null,
      o.insight?this.insightPanel(o.insight):null,
    ];
    return this.card(title, body, o);
  }

  /* The payload ships {title,what,why,risk,opportunity,action,priority} for ten
     keys across eight months -- 80 written analyses that the app has never once
     rendered. Collapsed by default so they never push the chart off screen. */
  insightPanel(key){
    const api = this.state.api; if(!api) return null;
    const it = api.insight(this.state.filters.month, key);
    if(!it) return null;                       // no data for this month: show nothing
    const open = (this.state.ins||{})[key];
    const pr = it.priority||"";
    const col = pr.indexOf("عالية")>=0 ? "#ef4444" : pr.indexOf("متوسطة")>=0 ? "#f59e0b" : "#10b981";
    const row = (k,v)=>React.createElement("div",{key:k,style:{display:"flex",gap:7,padding:"5px 0",
        borderTop:"1px solid rgba(255,255,255,.05)"}},
      React.createElement("span",{style:{flex:"none",width:64,fontSize:10,color:"#64748b"}},k),
      React.createElement("span",{style:{flex:1,minWidth:0,fontSize:11,lineHeight:1.8,color:"#cbd5e1"}},v));
    return React.createElement("div",{key:"ins",style:{marginTop:2,borderRadius:12,
        background:"rgba(255,255,255,.02)",border:"1px solid rgba(255,255,255,.07)",
        borderInlineStart:"3px solid "+col, overflow:"hidden"}},
      React.createElement("div",{key:"h",onClick:()=>this.setState(st=>({ins:{...st.ins,[key]:!open}})),
        style:{display:"flex",alignItems:"center",gap:7,padding:"9px 11px",cursor:"pointer"}},
        React.createElement("span",{style:{flex:1,minWidth:0,fontSize:11.5,fontWeight:700,color:"#e2e8f0",
          overflow:"hidden",whiteSpace:"nowrap",textOverflow:"ellipsis"}},it.title),
        React.createElement("span",{style:{flex:"none",fontSize:9,padding:"2px 7px",borderRadius:99,
          background:col+"22",color:col,whiteSpace:"nowrap"}},"أولوية "+pr),
        React.createElement("span",{style:{flex:"none",fontSize:11,color:"#64748b"}},open?"▲":"▼")),
      open?React.createElement("div",{key:"b",style:{padding:"0 11px 10px"}},[
        row("ماذا حدث", it.what), row("لماذا", it.why), row("المخاطر", it.risk),
        row("الفرص", it.opportunity), row("الإجراء", it.action)]):null);
  }

  /* Customer statement, ported from the desktop's openDrill. Deliberately spans
     the whole year and ignores the month filter, as the source does -- a
     statement is a statement, not a month's slice. */
  statementSheet(code){
    const api = this.state.api, T = this.state.T, D = api.D;
    const inv = (D.invoices||[]).filter(v => String(v.customer_code)===String(code));
    const lines = (D.lines||[]).filter(l => String(l.customer_code)===String(code));
    if(!inv.length && !lines.length) return null;
    const byDate = (a,b)=>a.date<b.date?-1:1;
    const receipts = ((D.collections&&D.collections.receipts)||[])
      .filter(r=>String(r.customer_code)===String(code)).sort(byDate);
    const returns = ((D.collections&&D.collections.returns_rows)||[])
      .filter(r=>String(r.customer_code)===String(code)).sort(byDate);
    const ar = (D.customer_ar||{})[String(code)] || {};
    const name = (inv[0]&&inv[0].customer_name) || (lines[0]&&lines[0].customer_name) || code;
    const rep = ar.rep || (inv[0]&&inv[0].rep) || "غير محدد";
    const totColl = receipts.reduce((a,r)=>a+(r.amount||0),0);
    const totRet = returns.reduce((a,r)=>a+(r.value||0),0);
    const billed = inv.reduce((a,v)=>a+(v.reported_total||0),0);
    const items = [...T.groupSum(lines,"item_name","line_total")].sort((a,b)=>b[1]-a[1]);

    const mk = (v,l,c)=>React.createElement("div",{key:l,style:{padding:"9px 10px",borderRadius:12,
        background:"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.07)",
        borderInlineStart:"3px solid "+(c||"#3b82f6")}},
      React.createElement("div",{style:{fontSize:13,fontWeight:800,color:"#f1f5f9",
        fontFamily:"'JetBrains Mono',monospace"}},v),
      React.createElement("div",{style:{fontSize:9.5,color:"#94a3b8",marginTop:2}},l));
    const tbl = (title, rows, cols, emptyMsg)=>React.createElement("div",{key:title,
        style:{display:"flex",flexDirection:"column",gap:6}},
      React.createElement("div",{style:{fontSize:12,fontWeight:700,color:"#e2e8f0",marginTop:4}},
        title+" ("+rows.length+")"),
      rows.length?this.rowsList(rows.slice(0,40), cols):this.empty(emptyMsg));
    const stat = {paid:"محصّلة", unpaid:"غير محصّلة", zero:"صفرية"};

    return React.createElement("div",{key:"st",onClick:()=>this.setState({stmt:null}),
        style:{position:"absolute",inset:0,zIndex:12,background:"rgba(3,6,14,.82)",
               display:"flex",alignItems:"flex-end"}},
      React.createElement("div",{onClick:e=>e.stopPropagation(),style:{width:"100%",maxHeight:"92%",
          overflow:"auto",background:"#0d1220",borderTop:"1px solid rgba(255,255,255,.12)",
          borderRadius:"22px 22px 0 0",padding:"14px 13px 26px",display:"flex",
          flexDirection:"column",gap:9}},
        React.createElement("div",{key:"g",style:{width:38,height:4,borderRadius:99,
          background:"rgba(255,255,255,.2)",margin:"0 auto 4px"}}),
        React.createElement("div",{key:"h",style:{display:"flex",alignItems:"baseline",gap:8}},
          React.createElement("b",{style:{fontSize:14,color:"#f1f5f9",flex:1,minWidth:0,
            overflow:"hidden",whiteSpace:"nowrap",textOverflow:"ellipsis"}},"كشف حساب — "+name),
          React.createElement("span",{onClick:()=>this.setState({stmt:null}),
            style:{fontSize:11,color:"#93c5fd",cursor:"pointer",flex:"none"}},"إغلاق")),
        React.createElement("div",{key:"r",style:{fontSize:10.5,color:"#64748b"}},
          "مندوب: "+rep+" · كل فواتير 2026 (لا يتأثر بفلتر الشهر)"),
        React.createElement("div",{key:"k",style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:7}},[
          mk(T.egpK(billed),"المُفوتر 2026","#3b82f6"),
          mk(T.egpK(totColl),"التحصيل الفعلي","#10b981"),
          mk(T.egpK(totRet),"المرتجعات","#ef4444"),
          mk(ar.outstanding==null?"—":T.egpK(ar.outstanding),"الرصيد النهائي","#f59e0b"),
          mk(ar.collection_rate==null?"—":T.pct(ar.collection_rate),"معدل التحصيل","#8b5cf6"),
          mk(T.pct(ar.bonus_pct||0,0),"الحافز","#06b6d4")]),
        tbl("الفواتير", inv, [["الفاتورة",r=>r.invoice_no],["التاريخ",r=>this.ltr(r.invoice_date)],
          ["الإجمالي",r=>T.num(r.reported_total)],["الحالة",r=>stat[r.status]||r.status],
          ["المدفوع",r=>T.num(r.paid)],["الباقي",r=>T.num(r.remaining)],
          ["الكمية",r=>T.int(r.qty_total)]], "لا توجد فواتير"),
        tbl("التحصيلات (نقدي فعلي)", receipts, [["التاريخ",r=>this.ltr(r.date)],
          ["المبلغ",r=>T.num(r.amount)],["طريقة الدفع",r=>r.method],["سند",r=>r.doc_ref||"—"],
          ["إيصال",r=>r.receipt_no||"—"],["المندوب",r=>r.rep]], "لا توجد تحصيلات مُطابَقة بالاسم"),
        tbl("المرتجعات", returns, [["التاريخ",r=>this.ltr(r.date)],
          ["القيمة",r=>T.num(r.value)],["مرجع الفاتورة",r=>r.invoice_ref||"—"],
          ["المندوب",r=>r.rep]], "لا توجد مرتجعات"),
        tbl("الأصناف المشتراة", items.map(e=>({n:e[0],v:e[1]})),
          [["الصنف",r=>r.n],["القيمة",r=>T.num(r.v)]], "لا توجد أصناف")));
  }

  /* ---- filter bar (window.DASH path) --------------------------------------
     The desktop dashboard's filter row, laid out for a phone: labelled native
     <select>s in a 2-column grid. Native pickers handle 233 customers and 87
     items without a custom list, and open the OS wheel on mobile.

     Option lists are derived from the selected month only. Narrowing them by
     every active filter would look tidier but creates dead ends — pick a
     customer and the rep list collapses to one entry you cannot leave. */
  /* ---- أعمار المديونية لكل عميل -------------------------------------------
     An AR snapshot is a point in time, so this section deliberately ignores the
     month / item / brand / status filters (which slice sales) and honours only
     the customer and rep filters, which slice the ledger. Stated on the card. */
  /* U+2066 LEFT-TO-RIGHT ISOLATE … U+2069 POP. Without this an ISO date inside
     an Arabic sentence is reordered by the bidi algorithm and renders as
     30-07-2026, or splits across a line break mid-date. */
  ltr(x){ return "\u2066" + String(x) + "\u2069"; }

  /* Same isolation, but as an element, so the date can also be kept from
     wrapping mid-way when it sits inside a paragraph of Arabic. */
  dateEl(x,k){ return React.createElement("span",{key:k||"d",
    style:{whiteSpace:"nowrap",unicodeBidi:"isolate",direction:"ltr"}}, String(x)); }

  agingCohort(D, f){
    if(f.customer) return new Set([String(f.customer)]);
    if(f.rep) return new Set(((D.receivables&&D.receivables.rows)||[])
      .filter(r=>r.rep===f.rep).map(r=>String(r.customer_code)));
    return null;
  }

  agingBody(X, T, api){
    const AG = this.state.AG, C = this.state.C, D = api.D, f = this.state.filters;
    const rows = AG.agingFor(D, this.agingCohort(D, f));
    if(!rows.length) return [this.card("أعمار المديونية",this.empty("لا يوجد عملاء في هذا التقسيم"),{k:"ag0"})];
    const t = AG.agingTotals(rows);
    const src = AG.sourceBuckets(rows, D);
    const scoped = !!(f.customer || f.rep);

    const kpis = [
      ["المديونية القائمة", T.egpK(t.snapshot), "لقطة "+this.ltr(D.meta.as_of), "#f59e0b"],
    ].concat(AG.AGE_TIERS.map(x=>[x.label, T.egpK(t.tiers[x.key]),
        t.snapshot?((t.tiers[x.key]/t.snapshot*100).toFixed(1)+"% من الرصيد"):"", x.color]))
     .concat([[AG.OPENING.label, T.egpK(t.opening), t.openingShare.toFixed(1)+"% من الرصيد", AG.OPENING.color]]);

    const kpiEl = React.createElement("div",{key:"agk",style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:7}},
      kpis.map((d,i)=>React.createElement("div",{key:i,style:{padding:"11px 11px 9px",borderRadius:14,
          background:"rgba(17,24,39,.85)",border:"1px solid rgba(255,255,255,.08)",
          borderInlineStart:"3px solid "+d[3],display:"flex",flexDirection:"column",gap:3}},
        React.createElement("span",{style:{fontSize:15,fontWeight:800,color:"#f1f5f9",fontFamily:"'JetBrains Mono',monospace"}},d[1]),
        React.createElement("span",{style:{fontSize:10.5,color:"#94a3b8",lineHeight:1.5}},d[0]),
        d[2]?React.createElement("span",{style:{fontSize:9.5,color:"#64748b"}},d[2]):null)));

    const tierBars = AG.AGE_TIERS.map(x=>[x.label, t.tiers[x.key], x.color])
      .concat([[AG.OPENING.label, t.opening, AG.OPENING.color]]);

    const repRows = AG.agingByRep(rows);

    /* The two views disagree by construction; the delta is shown rather than
       reconciled away, because it is the substantive finding. */
    const reconRows = [
      ["إجمالي الرصيد (الطريقتان)", T.egp(t.snapshot)],
      ["مجموع الشرائح + الافتتاحي − الزائد", T.egp(t.aged + t.opening - t.overpaid)],
      ["فرق التسوية", T.egp(t.reconDelta)],
      ["— حسب هذه اللوحة: غير مؤرَّخ (افتتاحي)", T.egp(t.opening)],
      ["— حسب المصدر: جاري (غير مستحق)", T.egp(src.current)],
    ];

    return [
      React.createElement("div",{key:"note",style:{padding:"11px 12px",borderRadius:12,
          background:"rgba(42,120,214,.09)",border:"1px solid rgba(42,120,214,.26)",
          fontSize:11,lineHeight:1.85,color:"#bfdbfe"}},
        ["العمر محسوب من تاريخ الفاتورة: تُرتَّب فواتير كل عميل من الأقدم، وتُطبَّق عليها سنداته "
         +"وتحصيلاته ومرتجعاته بتواريخها (FIFO)، وما يتبقّى مفتوحًا يُعمَّر بـ ",
         this.dateEl(D.meta.as_of,"asof"),
         " − تاريخ الفاتورة. المجموع يطابق رصيد اللقطة بالضبط."
         +(scoped?" · التقسيم الحالي: "+(f.customer?"عميل واحد":"مندوب واحد")+"."
                 :" · لقطة على مستوى الشركة.")]),

      kpiEl,

      this.chartCard("توزيع الرصيد حسب عمر الفاتورة",
        C.donut(tierBars.map(x=>[x[0],x[1],x[2]]),T.egp),
        {k:"ag1",h:C.H.base,sub:"لقطة "+this.ltr(D.meta.as_of)+" — لا تتأثر بفلتر الشهر"}),

      this.card("لماذا يوجد «رصيد افتتاحي»؟",React.createElement("div",
          {style:{fontSize:11.5,lineHeight:1.95,color:"#cbd5e1"}},
        ["الفواتير في المصدر تبدأ من ",
         this.dateEl((D.invoices&&D.invoices.length)?D.invoices.reduce((a,v)=>v.invoice_date<a?v.invoice_date:a,"9999"):"—","first"),
        "، لكن المديونية أقدم من ذلك. ما لا تستطيع الحركات المؤرَّخة تفسيره ("
        +T.egpK(t.opening)+"، أي "+t.openingShare.toFixed(1)
        +"% من الرصيد) يُعرض هنا كرصيد افتتاحي بعمر غير معروف بدلًا من إدراجه في شريحة عمرية. "
        +"لوحة المصدر توزّع الرصيد النهائي بالكامل على فواتير 2026، فيظهر هذا الجزء لديها ضمن «جاري (غير مستحق)» "
        +"("+T.egpK(src.current)+"). الطريقتان تعطيان نفس الإجمالي وتختلفان في التوزيع فقط."]),
        {k:"ag2",approx:true}),

      this.chartCard("الرصيد حسب المندوب",
        C.donut(repRows.map((r,i)=>[r.rep,r.snapshot,T.PAL[i%T.PAL.length]]),T.egp),
        {k:"ag3",h:C.H.base,sub:repRows.length+" مندوب"}),

      this.card("أعمار المديونية لكل عميل",this.rowsList(rows.slice(0,60),[
        ["العميل",r=>r.name],
        ["الرصيد",r=>T.num(r.snapshot)],
        ["أقل من شهر",r=>T.num(r.tiers.lt30)],
        ["شهر–شهرين",r=>T.num(r.tiers.m1_2)],
        ["شهرين–3 شهور",r=>T.num(r.tiers.m2_3)],
        ["أكثر من 3 شهور",r=>T.num(r.tiers.gt90)],
        ["رصيد افتتاحي",r=>T.num(r.opening)],
        ["سداد رصيد سابق",r=>r.overpaid?T.num(r.overpaid):"—"],
        ["أقدم فاتورة مفتوحة",r=>r.oldestInvoiceDate?this.ltr(r.oldestInvoiceDate):"—"],
        ["عمرها (يوم)",r=>r.oldestAge==null?"—":r.oldestAge],
        ["فواتير مفتوحة",r=>r.nOpenInvoices],
        ["المندوب",r=>r.rep]]),
        {k:"ag4",sub:rows.length+" عميل — مرتّبون بثقل الدين الأقدم"}),

      this.card("التسوية مع أعمار المصدر",React.createElement("div",{style:{display:"flex",flexDirection:"column"}},
        reconRows.map((r,i)=>React.createElement("div",{key:i,style:{display:"flex",justifyContent:"space-between",
            gap:12,padding:"7px 0",borderBottom:"1px solid rgba(255,255,255,.06)",fontSize:11.5}},
          React.createElement("span",{style:{color:"#94a3b8"}},r[0]),
          React.createElement("b",{style:{color:"#e2e8f0",fontFamily:"'JetBrains Mono',monospace"}},r[1])))
        .concat([React.createElement("div",{key:"n",style:{marginTop:9,fontSize:10.5,lineHeight:1.8,color:"#64748b"}},
          "سندات التحصيل والمرتجعات في المصدر غير مرتبطة بأرقام فواتير (لا يطابق أي منها رقم فاتورة حقيقيًا)، "
          +"لذلك يُطبَّق FIFO على مستوى العميل بالتاريخ لا فاتورةً بفاتورة — وهو نفس القيد الذي تصف به اللوحة الأصلية أعمارها بأنها «تقديرية».")])),
        {k:"ag5",approx:true}),

      this.chartCard("أعمار المصدر (أساس تاريخ الاستحقاق)",
        C.agingBar({buckets:src},D),
        {k:"ag6",approx:true,h:C.H.base,sub:"مهلة سداد "+D.meta.net_terms_days+" يومًا"})];
  }

  fOpts(api, month){
    const key = month || "all";
    if(this._optKey === key) return this._opts;
    const D = api.D, mAll = !month || month === "all";
    const inv = (D.invoices||[]).filter(v => mAll || v.month === month);
    const lns = (D.lines||[]).filter(l => mAll || l.month === month);
    const rank = (rows, kf, lf, vf) => {
      const m = new Map();
      for(const r of rows){ const k = kf(r); if(k==null||k==="") continue;
        const e = m.get(k) || [lf(r), 0]; e[1] += vf(r)||0; m.set(k, e); }
      return [...m.entries()].sort((a,b)=>b[1][1]-a[1][1]).map(([k,v])=>[k, v[0]]);
    };
    this._optKey = key;
    this._opts = {
      customer: rank(inv, v=>v.customer_code, v=>v.customer_name, v=>v.reported_total),
      rep:      rank(inv, v=>v.rep,           v=>v.rep,           v=>v.reported_total),
      item:     rank(lns, l=>l.item_code,     l=>l.item_name,     l=>l.line_total),
      brand:    rank(lns, l=>l.brand,         l=>l.brand,         l=>l.line_total),
      status:   (D.invoices ? [["unpaid","غير محصّلة"],["paid","محصّلة"],["zero","صفرية"]] : []),
      aging:    (D.receivables&&D.receivables.bucket_labels)
                  ? Object.keys(D.receivables.bucket_labels).map(k=>[k, D.receivables.bucket_labels[k]]) : [],
      branch:   [],   // no branch field exists in invoices or lines
    };
    return this._opts;
  }

  filterBar(X, T, api){
    const f = this.state.filters, D = api.D;
    const opts = this.fOpts(api, f.month);
    const q = (this.state.fq||"").trim();
    const nActive = ["customer","rep","item","brand","status","aging"].filter(k=>f[k]).length
                  + ((f.month && f.month!=="all") ? 1 : 0);

    const SEL = {width:"100%",padding:"8px 9px",borderRadius:10,fontSize:12,fontFamily:"inherit",
      background:"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.10)",
      color:"#e2e8f0",appearance:"none",WebkitAppearance:"none",boxSizing:"border-box"};
    const OPT = {background:"#111827",color:"#e2e8f0"};

    const field = (label, node, note) => React.createElement("div",{key:label,
        style:{display:"flex",flexDirection:"column",gap:4,minWidth:0}},
      React.createElement("span",{style:{fontSize:10,color:"#64748b"}},label),
      node,
      note?React.createElement("span",{style:{fontSize:9,color:"#f59e0b"}},note):null);

    const select = (key, label, list, allLabel, filterByQ) => {
      let L = list;
      if(filterByQ && q) L = L.filter(o => String(o[1]).indexOf(q) !== -1);
      const on = !!f[key];
      return field(label, React.createElement("select",{
          value: f[key]||"", disabled: !L.length,
          onChange: e => this.set(key, e.target.value),
          style: {...SEL, opacity:L.length?1:.45,
                  color:on?"#93c5fd":"#e2e8f0", fontWeight:on?700:400,
                  borderColor:on?"rgba(42,120,214,.45)":"rgba(255,255,255,.10)"}},
        [React.createElement("option",{key:"__all",value:"",style:OPT}, allLabel||"الكل")]
          .concat(L.map(o=>React.createElement("option",{key:o[0],value:o[0],style:OPT},o[1])))),
        L.length ? null : "غير متاح بالمصدر");
    };

    const months = [["all", api.ALL_LABEL]].concat((D.meta.available_months||[])
      .map(m=>[m.v, m.l + (api.monthHasData(m.v) ? "" : " — لا توجد بيانات")]));

    return React.createElement("div",{style:{flex:"none",position:"relative",padding:"10px 13px 11px",
        borderBottom:"1px solid rgba(255,255,255,.06)",background:"rgba(13,18,32,.55)",
        display:"flex",flexDirection:"column",gap:8}},

      React.createElement("div",{key:"g",style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}},
        field("السنة", React.createElement("div",{style:{...SEL,color:"#94a3b8"}},"2026")),
        field("الشهر", React.createElement("select",{value:f.month||"all",
            onChange:e=>this.set("month", e.target.value),
            style:{...SEL,color:"#93c5fd",fontWeight:700,borderColor:"rgba(42,120,214,.45)"}},
          months.map(m=>React.createElement("option",{key:m[0],value:m[0],style:OPT},m[1])))),
        select("customer","العميل",opts.customer,"الكل",true),
        select("rep","المندوب",opts.rep,"الكل"),
        select("item","الصنف",opts.item,"الكل",true),
        select("brand","العلامة/الفئة",opts.brand,"الكل"),
        select("branch","الفرع",opts.branch,"كل الفروع"),
        select("status","حالة الفاتورة",opts.status,"الكل"),
        select("aging","فئة العمر",opts.aging,"الكل")),

      React.createElement("div",{key:"r",style:{display:"flex",alignItems:"center",gap:8}},
        React.createElement("input",{value:this.state.fq||"", placeholder:"بحث سريع… (عميل أو صنف)",
          onChange:e=>this.setState({fq:e.target.value}),
          style:{flex:1,minWidth:0,padding:"8px 10px",borderRadius:10,fontSize:12,fontFamily:"inherit",
            background:"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.10)",
            color:"#e2e8f0",boxSizing:"border-box"}}),
        React.createElement("span",{onClick:()=>this.setState({fq:"",
            filters:{month:D.meta.default_month||"all",customer:"",rep:"",brand:"",item:"",status:"",aging:""}}),
          style:{flex:"none",padding:"8px 12px",borderRadius:10,fontSize:11.5,cursor:"pointer",
            background:nActive?"rgba(227,73,72,.14)":"rgba(255,255,255,.03)",
            border:"1px solid "+(nActive?"rgba(227,73,72,.32)":"rgba(255,255,255,.10)"),
            color:nActive?"#fca5a5":"#94a3b8",whiteSpace:"nowrap"}},
          "إعادة تعيين"+(nActive?" ("+nActive+")":""))));
  }

  /* Two extracts ship together and cover different ground, so switching is
     explicit and both spans are labelled — merging them would produce totals
     that belong to neither. */
  srcSwitch(){
    const st=this.state;
    if(!st.api && !st.RD) return null;
    const snaps=st.snaps||[];
    const SEL={flex:1,minWidth:0,padding:"7px 9px",borderRadius:9,fontSize:11,fontFamily:"inherit",
      background:"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.10)",
      color:"#e2e8f0",appearance:"none",WebkitAppearance:"none",boxSizing:"border-box"};
    const OPT={background:"#111827",color:"#e2e8f0"};
    const onDash = st.src==="dash";

    /* Two snapshots can share an as_of and still disagree, so both dates are
       shown -- the ledger date and the date the extract was generated. */
    const snapSel = snaps.length ? React.createElement("select",{key:"s",value:st.snap||"",
        disabled:!onDash, onChange:e=>this.pickSnapshot(e.target.value),
        style:{...SEL, opacity:onDash?1:.45,
               color:onDash?"#93c5fd":"#64748b", fontWeight:onDash?700:400,
               borderColor:onDash?"rgba(42,120,214,.45)":"rgba(255,255,255,.10)"}},
      snaps.map(o=>React.createElement("option",{key:o.key,value:o.key,style:OPT},o.label))) : null;

    const tab=(id,lab)=>{const on=st.src===id;
      return React.createElement("span",{key:id,onClick:()=>this.setState({src:id,sheet:null,stmt:null,
          section:id==="dash"?"overview":"fin"}),
        style:{flex:"none",padding:"7px 11px",borderRadius:9,cursor:"pointer",fontSize:11,
          whiteSpace:"nowrap",fontWeight:on?700:400,
          background:on?"rgba(42,120,214,.16)":"rgba(255,255,255,.03)",
          border:"1px solid "+(on?"rgba(42,120,214,.42)":"rgba(255,255,255,.08)"),
          color:on?"#93c5fd":"#94a3b8"}},lab);};

    const cur = snaps.find(x=>x.key===st.snap);
    return React.createElement("div",{style:{flex:"none",position:"relative",
        background:"rgba(13,18,32,.75)",borderBottom:"1px solid rgba(255,255,255,.06)",
        padding:"7px 11px",display:"flex",flexDirection:"column",gap:6}},
      React.createElement("div",{key:"r",style:{display:"flex",gap:6,alignItems:"center"}},
        st.api?tab("dash","تفصيلي"):null,
        st.RD?tab("repo","18 شهرًا"):null,
        snapSel,
        React.createElement("label",{key:"ld",style:{flex:"none",padding:"6px 8px",borderRadius:9,
            cursor:"pointer",fontSize:9.5,color:"#94a3b8",border:"1px solid rgba(255,255,255,.10)",
            whiteSpace:"nowrap"}},"data.js",
          React.createElement("input",{type:"file",accept:".js,.json,text/javascript,application/json",
            style:{display:"none"},
            onChange:e=>{const f2=e.target.files&&e.target.files[0]; if(f2) this.loadDashFile(f2);}}))),
      React.createElement("div",{key:"m",style:{fontSize:9.5,color:"#64748b",lineHeight:1.6}},
        onDash
          ? (cur ? (cur.note+" · لقطة "+this.ltr(cur.as_of)+" · استُخرجت "+this.ltr(cur.generated))
                 : (st.api?("لقطة "+this.ltr(st.api.D.meta.as_of)):""))
          : (st.RD?("مجمّع 18 شهرًا · "+this.ltr(st.RD.financial.period.start+" → "+st.RD.financial.period.end)
                    +" · "+st.RD.eda_summary.n_customers+" عميل"):"")),
      st.loadMsg?React.createElement("div",{key:"lm",onClick:()=>this.setState({loadMsg:null}),
        style:{fontSize:10.5,lineHeight:1.7,cursor:"pointer",
          color:st.loadMsg.indexOf("تعذّر")===0?"#fca5a5":"#86efac"}},st.loadMsg):null);
  }

  kpiGrid(k,T,api){
    const D=api.D, f=this.state.filters;
    const keys=(D.monthly||[]).map(m=>m.month);
    const mon=Object.fromEntries((D.monthly||[]).map(m=>[m.month,m.net_sales]));
    const cm=(f.month&&f.month!=="all")?f.month:null;
    let salesSub="كل شهور 2026", salesCls="na";
    if(cm){ const i=keys.indexOf(cm), pk=i>0?keys[i-1]:null, pv=pk?mon[pk]:0;
      const dv=pv?(k.total_sales-pv)/pv:0;
      salesSub=pk?((dv>=0?"▲ ":"▼ ")+T.pct(Math.abs(dv))+" مقابل "+api.monthName(pk)):"";
      salesCls=dv>=0?"up":"down"; }
    const col={up:"#10b981",down:"#ef4444",na:"#64748b"};
    return React.createElement("div",{key:"kpi",style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:7}},
      T.KPI_DEFS.map((d,i)=>{
        const val=d.fixed!=null?d.fixed:T.FMT[d.fmt](k[d.key]);
        let sub=d.sub||"", cls=d.subCls||"na";
        if(d.momSub){ sub=salesSub; cls=salesCls; }
        if(d.subAsOf) sub="لقطة "+D.meta.as_of;
        if(d.subAvg) sub="متوسط "+T.egpK(k.avg_invoice_value);
        return React.createElement("div",{key:i,style:{padding:"11px 11px 9px",borderRadius:14,background:"rgba(17,24,39,.85)",border:"1px solid rgba(255,255,255,.08)",borderInlineStart:"3px solid "+d.accent,display:"flex",flexDirection:"column",gap:3}},
          React.createElement("span",{style:{color:d.accent,display:"block",height:16},dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round">'+T.KPI_ICONS[d.icon]+'</svg>'}}),
          React.createElement("span",{style:{fontSize:16,fontWeight:800,color:"#f1f5f9",fontFamily:"'JetBrains Mono',monospace"}},val),
          React.createElement("span",{style:{fontSize:10.5,color:"#94a3b8",lineHeight:1.5}},d.label),
          sub?React.createElement("span",{style:{fontSize:9.5,color:col[cls]}},sub):null);
      }));
  }

  sectionBody(X,T,api){
    const st=this.state, s=st.section, D=api.D, C=st.C, f=st.filters;
    if(s==="aging") return this.agingBody(X,T,api);
    if(s==="armove") return this.arMoveBody(X,T,api);

    const bl=k=>(D.receivables&&D.receivables.bucket_labels)?D.receivables.bucket_labels[k]:k;
    /* Tap handlers: map a click on a category chart back onto a filter. */
    const setF=(k,v)=>this.set(k,v);
    const pickCat=(key,cats)=>(p,o)=>{ const list=cats||(o&&o._cats); if(!list) return;
      const v=list[p.dataIndex!=null?p.dataIndex:0]; if(v!=null) setF(key,v); };
    const pickName=key=>p=>{ if(p&&p.name) setF(key,p.name); };
    const drill=(p,o)=>{ const c=o&&o._codes&&o._codes[p.dataIndex]; if(c!=null) this.setState({stmt:c}); };
    const brandPairs=()=>[...T.groupSum(X.lines,"brand","line_total")].sort((a,b)=>b[1]-a[1]);

    if(s==="overview") return [
      this.kpiGrid(X.kpis,T,api),
      this.chartCard("اتجاه المبيعات الشهري", C.monthly(D,f), {k:"c1",sub:"السلسلة الكاملة",insight:"monthly_trend"}),
      this.chartCard("المبيعات والتحصيل اليومي", C.daily(X), {k:"c2"}),
      this.chartCard("أعمار الديون", C.agingBar(X,D), {k:"c3",approx:true,insight:"aging",
        onPick:pickCat("aging")}),
      this.chartCard("معدل التحصيل التراكمي", C.gauge(X.kpis.collection_rate,"معدل التحصيل"),
        {k:"c4",h:C.H.short}),
      this.chartCard("توزيع المبيعات حسب العلامة", C.donut(brandPairs()),
        {k:"c5",h:C.H.short,onPick:pickName("brand")}),
      this.chartCard("أعلى 10 عملاء", C.topCustomers(X,10),
        {k:"c6",insight:"top_customers",onPick:drill})];

    if(s==="sales") return [
      this.chartCard("اتجاه المبيعات اليومي", C.daily(X), {k:"s1",insight:"monthly_trend"}),
      this.chartCard("تحليل التباين الشهري (شهر مقابل شهر)", C.variance(D), {k:"s2"}),
      this.chartCard("جسر المبيعات حسب العلامة", C.salesWaterfall(X), {k:"s3"}),
      this.chartCard("أعلى 12 صنفًا", C.topProducts(X,12), {k:"s4",onPick:(p,o)=>{
        const c=o._codes&&o._codes[p.dataIndex]; if(c!=null) setF("item",c);}}),
      this.card("بنود الفواتير",this.rowsList(X.lines.slice(0,40),[["الصنف",r=>r.item_name],["الفاتورة",r=>r.invoice_no],["العميل",r=>r.customer_name],["الإجمالي",r=>T.num(r.line_total)],["التاريخ",r=>this.ltr(r.invoice_date)],["المندوب",r=>r.rep],["العلامة",r=>r.brand],["الكمية",r=>T.int(r.qty)],["السعر",r=>T.num(r.unit_price)]]),{sub:X.lines.length+" بند",k:"s5"})];

    if(s==="customers") return [
      this.chartCard("أعلى 12 عميلًا", C.topCustomers(X,12),
        {k:"u1",insight:"top_customers",onPick:drill}),
      this.chartCard("تحليل باريتو (80/20)", C.pareto(X), {k:"u2",insight:"pareto",onPick:drill}),
      this.chartCard("مقارنة أعلى 5 عملاء (رادار)", C.radar(X), {k:"u3",h:C.H.tall}),
      this.chartCard("المبيعات مقابل المديونية", C.scatter(X),
        {k:"u4",sub:"حجم النقطة = المبيعات",onPick:drill}),
      this.card("ترتيب العملاء",this.rowsList(X.customers.slice(0,40),[["العميل",r=>r.customer_name],["المبيعات",r=>T.num(r.sales)],["المندوب",r=>r.rep],["المديونية",r=>r.outstanding==null?"—":T.num(r.outstanding)],["#",r=>r.rank],["الفواتير",r=>r.n_invoices],["الأصناف",r=>r.n_items],["الكراتين",r=>T.int(r.boxes)],["متوسط الفاتورة",r=>T.num(r.avg_invoice_value)],["معدل التحصيل",r=>r.collection_rate==null?"—":T.pct(r.collection_rate)],["الحافز %",r=>T.pct(r.bonus_pct,0)],["أقدم فاتورة",r=>r.oldest_invoice_no||"—"],["أيام التأخر",r=>r.oldest_days_overdue==null?"—":r.oldest_days_overdue]],r=>this.setState({stmt:r.customer_code})),{sub:X.customers.length+" عميل · اضغط لكشف الحساب",k:"u5"})];

    if(s==="products") return [
      this.chartCard("أعلى 12 صنفًا", C.topProducts(X,12), {k:"p1",insight:"top_products"}),
      this.chartCard("خريطة الإيراد (علامة ← صنف)", C.treemap(X), {k:"p2",h:C.H.tall}),
      this.chartCard("تشتت سعر البيع لأعلى الأصناف", C.priceBox(X), {k:"p3"}),
      this.chartCard("توزيع الإيراد حسب العلامة", C.donut(brandPairs()),
        {k:"p4",h:C.H.short,onPick:pickName("brand")}),
      this.card("أداء المنتجات",this.rowsList(X.products.slice(0,40),[["الصنف",r=>r.item_name],["المبيعات",r=>T.num(r.sales)],["العلامة",r=>r.brand],["المساهمة",r=>r.contribution_pct.toFixed(1)+"%"],["#",r=>r.rank],["الكمية",r=>T.int(r.qty)],["الكراتين",r=>T.int(r.boxes)],["م. السعر",r=>T.num(r.asp)],["أعلى سعر",r=>r.max_price==null?"—":T.num(r.max_price)],["أدنى سعر",r=>r.min_price==null?"—":T.num(r.min_price)],["العملاء",r=>r.n_customers]]),{k:"p5"})];

    if(s==="receivables") return [
      this.chartCard("أعمار الديون", C.agingBar(X,D),
        {k:"r1",approx:true,insight:"aging",onPick:pickCat("aging")}),
      this.chartCard("تراكم الأعمار (Waterfall)", C.agingWaterfall(X,D), {k:"r2",approx:true}),
      this.chartCard("المديونية حسب المندوب", C.byRep(X),
        {k:"r3",insight:"receivables_rep",onPick:pickCat("rep")}),
      this.chartCard("جاري مقابل متأخرات",
        C.donut([["جاري",T.sum(X.recv,"current"),"#10b981"],["متأخرات",T.sum(X.recv,"overdue"),"#ef4444"]]),
        {k:"r4",h:C.H.short}),
      this.card("المديونية حسب العميل",this.rowsList(X.recv.slice(0,40),[["العميل",r=>r.customer_name],["الرصيد",r=>T.num(r.outstanding)],["متأخرات",r=>T.num(r.overdue)],["الفئة",r=>bl(r.bucket)],["المندوب",r=>r.rep],["جاري",r=>T.num(r.current)],["أيام التأخر",r=>r.days_overdue],["آخر نشاط",r=>this.ltr(r.last_invoice_date)]],r=>this.setState({stmt:r.customer_code})),{approx:true,k:"r5",sub:"اضغط لكشف الحساب"})];

    if(s==="collections"){
      const Co=D.collections||{};
      const rate=Co.billed_2026?Math.max(0,Math.min(1,Co.grand_total_collected/Co.billed_2026)):0;
      const methodPairs=[...T.groupSum(((Co.receipts)||[]).filter(r=>!f.month||f.month==="all"||r.month===f.month),"method","amount")]
        .filter(e=>e[1]>0).sort((a,b)=>b[1]-a[1]);
      const rr=[["إجمالي المُفوتر 2026",T.egp(Co.billed_2026)],["التحصيل النقدي الفعلي",T.egp(Co.grand_total_collected)],["المرتجعات",T.egp(Co.grand_total_returns)],["المديونية القائمة",T.egp(Co.outstanding_as_of!=null?Co.outstanding_as_of:Co.outstanding_1607)],["معدل التحصيل الفعلي",T.pct(rate)]];
      const A2=Co.attribution||{};
      return [
        this.chartCard("معدل التحصيل الفعلي (تراكمي 2026)", C.gauge(rate,"تحصيل ÷ مُفوتر"),
          {k:"o1",h:C.H.short,sub:"سنوي — لا يتأثر بفلتر الشهر"}),
        this.card("التسوية — جسر التحصيل",React.createElement("div",{style:{display:"flex",flexDirection:"column"}},
          rr.map((r,i)=>React.createElement("div",{key:i,style:{display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:"1px solid rgba(255,255,255,.06)",fontSize:12}},
            React.createElement("span",{style:{color:"#94a3b8"}},r[0]),
            React.createElement("b",{style:{color:"#e2e8f0",fontFamily:"'JetBrains Mono',monospace"}},r[1])))
          .concat([React.createElement("div",{key:"n",style:{marginTop:8,fontSize:10,lineHeight:1.75,color:"#64748b"}},
            "جسر تقريبي (لا يتضمن رصيد أول المدة)؛ الإجماليان النقديان مطابقان لمستندَي المصدر بالضبط."
            +(A2.receipts_unmatched?" سدادات غير مُطابَقة بالاسم: "+A2.receipts_unmatched+" ("+T.egp(A2.unmatched_collected)+").":""))])),{k:"o2"}),
        this.chartCard("المبيعات مقابل التحصيل والمرتجعات (شهري 2026)", C.collectionsMonthly(D,f),
          {k:"o3",h:C.H.tall,sub:"جسر تدفق نقدي شهري"}),
        this.chartCard("التحصيل حسب طريقة الدفع", C.donut(methodPairs), {k:"o4",h:C.H.short}),
        this.chartCard("التحصيل والمرتجعات حسب المندوب", C.collectionsByRep(D,f),
          {k:"o5",onPick:pickCat("rep")}),
        this.chartCard("أدنى 15 عميلًا في معدل التحصيل", C.worstCollectors(X), {k:"o6",onPick:drill}),
        this.card("سجل السدادات",this.rowsList((Co.receipts||[]).slice(0,40),[["العميل",r=>r.customer_name],["المبلغ",r=>T.num(r.amount)],["التاريخ",r=>this.ltr(r.date)],["طريقة الدفع",r=>r.method],["المندوب",r=>r.rep],["سند",r=>r.doc_ref||"—"],["إيصال",r=>r.receipt_no||"—"]]),{k:"o7"}),
        this.card("سجل المرتجعات",this.rowsList((Co.returns_rows||[]).slice(0,40),[["العميل",r=>r.customer_name],["القيمة",r=>T.num(r.value)],["التاريخ",r=>this.ltr(r.date)],["مرجع الفاتورة",r=>r.invoice_ref||"—"],["المندوب",r=>r.rep]]),{k:"o8"})];
    }

    if(s==="bonus"){
      const tot=X.customers.reduce((a,c)=>a+(c.bonus_value||0),0);
      return [
        this.chartCard("توزيع العملاء على شرائح الحافز", C.bonusDist(X), {k:"b1",insight:"bonus"}),
        this.card("سلّم الحافز",React.createElement("div",{style:{display:"flex",flexDirection:"column"}},
          T.BONUS_RULES.map((r,i)=>React.createElement("div",{key:i,style:{display:"flex",justifyContent:"space-between",padding:"7px 0",borderBottom:"1px solid rgba(255,255,255,.06)",fontSize:12}},
            React.createElement("span",{style:{color:"#94a3b8"}},r[0]),
            React.createElement("b",{style:{color:"#e2e8f0"}},r[1]))).concat([
            React.createElement("div",{key:"t",style:{marginTop:9,fontSize:12,color:"#94a3b8"}},"إجمالي الحافز المستحق: ",
              React.createElement("b",{style:{color:"#10b981",fontFamily:"'JetBrains Mono',monospace"}},T.egp(tot)))])),{k:"b2"}),
        this.card("تقرير الحوافز",this.rowsList(X.customers.filter(c=>c.has_ar).slice(0,40),[["العميل",r=>r.customer_name],["قيمة الحافز",r=>T.num(r.bonus_value)],["الحافز %",r=>T.pct(r.bonus_pct,0)],["معدل التحصيل",r=>r.collection_rate==null?"—":T.pct(r.collection_rate)],["المندوب",r=>r.rep],["مبيعات الشهر",r=>T.num(r.sales)],["إجمالي مُفوتر",r=>T.num(r.total_billed)],["المديونية",r=>r.outstanding==null?"—":T.num(r.outstanding)]],r=>this.setState({stmt:r.customer_code})),{k:"b3",sub:"اضغط لكشف الحساب"})];
    }

    if(s==="analytics") return [
      this.chartCard("شمسية: مندوب ← صنف", C.sunburst(X), {k:"a1",h:C.H.tall,insight:"pareto"}),
      this.chartCard("تدفق: عميل ← صنف", C.sankey(X), {k:"a2",h:C.H.tall,
        sub:"أعلى 5 عملاء × 5 أصناف — رأسي ليتّسع للشاشة"}),
      this.chartCard("حرارية: مندوب × علامة", C.heatmap(X), {k:"a3",h:C.H.tall,
        onPick:p=>{ const o=C.heatmap(X); if(o&&o._rows&&p.data) setF("rep",o._rows[p.data[1]]); }}),
      this.chartCard("توزيع قيم الفواتير", C.histogram(X), {k:"a4"})];

    const q=D.data_quality||{};
    const stats=[[T.pct(q.reconciliation_rate),"مطابقة الإجماليات","#10b981"],[T.int(q.n_line_items),"بنود الفواتير","#3b82f6"],[T.int(q.n_invoices),"عدد الفواتير","#8b5cf6"],[T.int(q.missing_total),"قيم مفقودة","#f59e0b"],[T.int(q.duplicate_invoice_count),"فواتير مكررة","#f97316"],[T.int(q.zero_value_invoice_count),"فواتير صفرية","#ef4444"],[T.int(q.abnormal_price_count),"أسعار شاذّة","#ec4899"],[T.int(q.abnormal_qty_count),"كميات شاذّة","#c4b5fd"]];
    return [
      this.kpiTiles(stats.map(x=>[x[1],x[0],"",x[2]]),"q"),
      this.chartCard("نسبة المطابقة", C.gauge(q.reconciliation_rate,"مطابقة"),
        {k:"q1",h:C.H.short,insight:"data_quality"}),
      this.chartCard("توزيع قيم الفواتير", C.histogram(X), {k:"q2"}),
      this.card("الفواتير صفرية القيمة",this.rowsList((D.zero_invoices||[]).slice(0,40),[["العميل",r=>r.customer_name],["الفاتورة",r=>r.invoice_no],["التاريخ",r=>this.ltr(r.invoice_date)],["الكمية",r=>T.int(r.qty_total)],["كود العميل",r=>r.customer_code],["بونص",r=>r.is_bonus?"نعم":"—"]]),{sub:"بونص / عيّنات",k:"q3",insight:"zero_invoices"})];
  }

  build(){
    const st=this.state, T=st.T, api=st.api, D=api.D, f=st.filters;
    /* SECTION_LABELS is kept verbatim from the source dashboard; the aging
       section is an addition, so it is appended here rather than edited in. */
    const SEC=T.SECTION_LABELS.concat([
      {id:"aging", label:"أعمار العملاء", h2:"أعمار المديونية لكل عميل",
       p:"العمر من تاريخ الفاتورة · FIFO بالتحصيلات والمرتجعات المؤرَّخة · يطابق رصيد اللقطة"},
      {id:"armove", label:"حركة المديونية", h2:"حركة المديونية بين لقطتين",
       p:"فرق رصيد كل عميل بين لقطتَي مديونية — تحليل غير متاح في لوحة الحاسوب"}]);
    const cur=SEC.find(s=>s.id===st.section)||SEC[0];
    const X=api.buildContext(f);
    const noData=!api.monthHasData(f.month);
    const NAV=[["overview","لوحة"],["sales","المبيعات"],["customers","العملاء"],["receivables","المديونية"]];

    const navEl=React.createElement("div",{style:{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:2}},
      NAV.map(([id,lab])=>{const on=st.section===id;
        return React.createElement("div",{key:id,onClick:()=>this.setState({section:id,sheet:null}),style:{display:"flex",flexDirection:"column",alignItems:"center",gap:4,padding:"6px 0",borderRadius:12,cursor:"pointer",background:on?"rgba(59,130,246,.12)":"transparent",color:on?"#93c5fd":"#64748b"}},
          React.createElement("span",{style:{width:19,height:19,display:"block"},dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round">'+T.KPI_ICONS[id==="overview"?"sales":id==="sales"?"money":id==="customers"?"users":"warn"]+'</svg>'}}),
          React.createElement("span",{style:{fontSize:9.5,fontWeight:on?700:400}},lab));})
      .concat([React.createElement("div",{key:"more",onClick:()=>this.setState({sheet:"nav"}),style:{display:"flex",flexDirection:"column",alignItems:"center",gap:4,padding:"6px 0",borderRadius:12,cursor:"pointer",color:["products","collections","bonus","analytics","quality","aging","armove"].includes(st.section)?"#93c5fd":"#64748b"}},
        React.createElement("span",{style:{fontSize:17,lineHeight:"19px"}},"⋯"),
        React.createElement("span",{style:{fontSize:9.5}},"المزيد"))]));

    /* The bar is open by default (it is the dashboard's primary control, as on
       the desktop); the header button collapses it to reclaim screen height. */
    const barOpen = !st.barHidden;
    const nA=["customer","rep","item","brand","status","aging"].filter(k=>f[k]).length;
    const filterBtnEl=React.createElement("span",{onClick:()=>this.setState({barHidden:barOpen}),style:{position:"relative",width:34,height:34,flex:"none",borderRadius:10,background:(barOpen||nA)?"rgba(42,120,214,.16)":"rgba(255,255,255,.03)",border:"1px solid "+((barOpen||nA)?"rgba(42,120,214,.45)":"rgba(255,255,255,.08)"),display:"grid",placeItems:"center",color:(barOpen||nA)?"#93c5fd":"#e2e8f0",cursor:"pointer"}},
      React.createElement("span",{key:"i",style:{display:"block",width:17,height:17},dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>'}}),
      nA?React.createElement("span",{key:"b",style:{position:"absolute",top:-4,insetInlineEnd:-4,minWidth:14,height:14,padding:"0 3px",borderRadius:99,background:"#2a78d6",color:"#fff",fontSize:9,fontWeight:800,lineHeight:"14px",textAlign:"center"}},String(nA)):null);
    const filterBarEl = barOpen ? this.filterBar(X,T,api) : null;
    const srcEl = this.srcSwitch();

    const active=T.FILTER_DEFS.filter(d=>d.key!=="year"&&d.key!=="month"&&f[d.key]);
    const chipsEl=React.createElement("div",{style:{flex:"none",position:"relative",display:"flex",alignItems:"center",gap:6,padding:"8px 13px",overflowX:"auto",borderBottom:"1px solid rgba(255,255,255,.06)"}},
      [React.createElement("span",{key:"h2",style:{fontSize:12,fontWeight:700,color:"#e2e8f0",flex:"none"}},cur.h2),
       React.createElement("span",{key:"m",onClick:()=>this.setState({sheet:"month"}),style:{flex:"none",fontSize:10.5,padding:"4px 9px",borderRadius:99,background:"rgba(59,130,246,.14)",border:"1px solid rgba(59,130,246,.3)",color:"#93c5fd",cursor:"pointer"}},api.curMonthLabel(f.month))]
      .concat(active.map(d=>React.createElement("span",{key:d.key,onClick:()=>this.set(d.key,""),style:{flex:"none",fontSize:10.5,padding:"4px 9px",borderRadius:99,background:"rgba(239,68,68,.14)",border:"1px solid rgba(239,68,68,.28)",color:"#fca5a5",cursor:"pointer"}},d.label+": "+f[d.key]+" ✕"))));

    let body=this.sectionBody(X,T,api);
    body=[React.createElement("div",{key:"sub",style:{fontSize:11,color:"#64748b",lineHeight:1.7}},cur.p)].concat(
      noData?[this.empty("لا توجد بيانات لهذا الشهر")]:body);

    let sheetEl=null;
    if(st.sheet==="export"){
      sheetEl=this.exportSheet();
    } else if(st.sheet){
      let inner;
      if(st.sheet==="nav"){
        inner=SEC.map(s=>React.createElement("div",{key:s.id,onClick:()=>this.setState({section:s.id,sheet:null}),style:{padding:"12px 13px",borderRadius:12,background:st.section===s.id?"rgba(59,130,246,.12)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.07)",fontSize:13,color:"#e2e8f0",cursor:"pointer"}},s.label));
      } else if(st.sheet==="month"){
        inner=[{v:"all",l:api.ALL_LABEL}].concat(D.meta.available_months||[]).map(m=>React.createElement("div",{key:m.v,onClick:()=>this.set("month",m.v==="all"?"all":m.v),style:{padding:"11px 13px",borderRadius:12,background:f.month===m.v?"rgba(59,130,246,.12)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.07)",fontSize:12.5,color:api.monthHasData(m.v)?"#e2e8f0":"#64748b",cursor:"pointer"}},m.l+(api.monthHasData(m.v)?"":" — لا توجد بيانات")));
      } else if(st.sheet==="filters"){
        const opts={customer:X.customers.map(c=>[c.customer_code,c.customer_name]),
          rep:[...new Set(X.lines.map(l=>l.rep))].filter(Boolean).map(r=>[r,r]),
          brand:[...new Set(X.lines.map(l=>l.brand))].filter(Boolean).map(b=>[b,b]),
          item:X.products.map(p=>[p.item_code,p.item_name]),
          status:(T.FILTER_DEFS.find(d=>d.key==="status").options),
          aging:T.AGING_KEYS.map(k=>[k,(D.receivables&&D.receivables.bucket_labels)?D.receivables.bucket_labels[k]:k]),
          branch:[]};
        inner=T.FILTER_DEFS.map(d=>{
          if(d.fixed) return React.createElement("div",{key:d.key,style:{fontSize:12,color:"#94a3b8"}},d.label+": ",React.createElement("b",{style:{color:"#e2e8f0"}},d.fixed));
          if(d.key==="month") return React.createElement("div",{key:d.key,onClick:()=>this.setState({sheet:"month"}),style:{fontSize:12,color:"#94a3b8",cursor:"pointer"}},d.label+": ",React.createElement("b",{style:{color:"#93c5fd"}},api.curMonthLabel(f.month)));
          const list=(opts[d.key]||[]).slice(0,40);
          return React.createElement("div",{key:d.key,style:{display:"flex",flexDirection:"column",gap:6}},
            React.createElement("span",{style:{fontSize:11,color:"#64748b"}},d.label),
            React.createElement("div",{style:{display:"flex",gap:5,flexWrap:"wrap"}},
              [React.createElement("span",{key:"all",onClick:()=>this.set(d.key,""),style:{fontSize:10.5,padding:"4px 9px",borderRadius:99,cursor:"pointer",background:!f[d.key]?"rgba(59,130,246,.14)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.08)",color:"#cbd5e1"}},d.all||"الكل")]
              .concat(list.length?list.map(o=>React.createElement("span",{key:o[0],onClick:()=>this.set(d.key,o[0]),style:{fontSize:10.5,padding:"4px 9px",borderRadius:99,cursor:"pointer",background:f[d.key]===o[0]?"rgba(59,130,246,.14)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.08)",color:"#cbd5e1"}},o[1]))
                :[React.createElement("span",{key:"na",style:{fontSize:10.5,color:"#64748b"}},"غير متاح بالمصدر")])));
        });
      } else {
        inner=[React.createElement("div",{key:"d",style:{display:"flex",flexDirection:"column"}},
          st.sheet.cols.map((c,i)=>React.createElement("div",{key:i,style:{display:"flex",justifyContent:"space-between",gap:12,padding:"8px 0",borderBottom:"1px solid rgba(255,255,255,.06)",fontSize:12}},
            React.createElement("span",{style:{color:"#64748b"}},c[0]),
            React.createElement("b",{style:{color:"#e2e8f0",fontFamily:"'JetBrains Mono',monospace"}},String(c[1](st.sheet.r)??"—")))))];
      }
      sheetEl=React.createElement("div",{onClick:()=>this.setState({sheet:null}),style:{position:"absolute",inset:0,zIndex:9,background:"rgba(3,6,14,.7)",display:"flex",alignItems:"flex-end"}},
        React.createElement("div",{onClick:e=>e.stopPropagation(),style:{width:"100%",maxHeight:"78%",overflow:"auto",background:"#111827",borderTop:"1px solid rgba(255,255,255,.10)",borderRadius:"22px 22px 0 0",padding:"14px 14px 26px",display:"flex",flexDirection:"column",gap:9}},
          [React.createElement("div",{key:"g",style:{width:38,height:4,borderRadius:99,background:"rgba(255,255,255,.2)",margin:"0 auto 6px"}})].concat(inner)));
    }

    const statusEl=React.createElement("div",null,
      React.createElement("b",{style:{color:"#10b981"}},"window.DASH متصل"),
      React.createElement("div",{style:{marginTop:6,lineHeight:1.9}},
        "as_of: "+D.meta.as_of+" · net_terms_days: "+D.meta.net_terms_days,
        React.createElement("br"),
        "lines: "+(D.lines||[]).length+" · invoices: "+(D.invoices||[]).length+" · بعد الفلترة: "+X.lines.length+" / "+X.invoices.length));

    const sectionListEl=React.createElement("div",{dir:"rtl",style:{display:"flex",flexWrap:"wrap",gap:6}},
      SEC.map(s=>React.createElement("span",{key:s.id,onClick:()=>this.setState({section:s.id}),style:{fontSize:11,padding:"5px 10px",borderRadius:99,cursor:"pointer",background:st.section===s.id?"rgba(59,130,246,.16)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.08)",color:"#cbd5e1"}},s.label)));

    const stmtEl = st.stmt!=null ? this.statementSheet(st.stmt) : null;
    return {bodyEl:body, navEl, chipsEl, filterBarEl, srcEl, filterBtnEl,
            exportBtnEl:this.exportBtn(),
            sheetEl:[sheetEl, stmtEl], statusEl, sectionListEl};
  }

  /* ---- window.DASH_DATA path (repo-adapter.js) ----
     Precomputed-aggregate schema from dashboards/data.js. No transactional
     filters exist in this schema (no per-line customer/rep/brand/month
     dimension to slice by), so the filter button is disabled here — every
     figure below is already the full-period aggregate the repo computes. */

  repoFin(R,RD){
    const fin=RD.financial;
    const arReps=[...(fin.ar_by_rep||[])].sort((a,b)=>b.net_balance-a.net_balance);
    return [
      this.kpiGridRepo(R.kpisFin(RD)),
      this.card("اتجاه المبيعات الشهرية (18 شهرًا)",this.lineChart(RD.monthly_series.map(m=>({v:m.revenue})),R.C.blue),{k:"f1",sub:"تفصيل التوقع في تبويب التنبؤ"}),
      this.card("رصيد المديونية حسب المندوب",this.barsH(arReps.map(r=>[r.rep,r.net_balance,R.C.indigo]),R.fmtEGPk),{k:"f2",sub:"لقطة 2026/7/4"}),
      this.card("تركّز المخاطر (HHI) وأيام الذمم",React.createElement("div",{style:{display:"flex",flexDirection:"column",gap:6,fontSize:11.5,color:"#94a3b8",lineHeight:1.8}},
        React.createElement("div",null,"العملاء: ",React.createElement("b",{style:{color:"#e2e8f0"}},R.fmt0(fin.hhi_customers))),
        React.createElement("div",null,"العلامات: ",React.createElement("b",{style:{color:"#e2e8f0"}},R.fmt0(fin.hhi_brands))," — تركّز مرتفع"),
        React.createElement("div",null,"الأصناف: ",React.createElement("b",{style:{color:"#e2e8f0"}},R.fmt0(fin.hhi_items))),
        React.createElement("div",null,"DSO تقريبي: ",React.createElement("b",{style:{color:"#e2e8f0"}},R.fmt1(fin.dso_proxy_days)+" يومًا"))),{k:"f3"})];
  }

  repoSales(R,RD){
    const cust=[...RD.customer_pareto].sort((a,b)=>b.line_total-a.line_total);
    const items=[...RD.item_abc_xyz].sort((a,b)=>b.line_total-a.line_total);
    const bottom10=[...RD.dim_items.filter(d=>d.n_lines>=5)].sort((a,b)=>a.total_revenue-b.total_revenue).slice(0,10);
    return [
      this.kpiGridRepo(R.kpisSales(RD)),
      this.card("أعلى 10 عملاء بالإيراد",this.barsH(cust.slice(0,10).map(c=>[c.customer_name,c.line_total,R.C.blue]),R.fmtEGPk),{k:"s1"}),
      this.card("أعلى 10 أصناف بالإيراد",this.barsH(items.slice(0,10).map(it=>[it.item_name_canonical,it.line_total,R.C.green]),R.fmtEGPk),{k:"s2"}),
      this.card("أدنى 10 أصناف أداءً",this.rowsList(bottom10,[["الصنف",r=>r.item_name],["العلامة",r=>r.brand],["الإيراد",r=>R.fmt0(r.total_revenue)],["الكمية",r=>R.fmt0(r.total_qty)]]),{k:"s3",sub:"استُبعدت الأصناف نادرة التكرار"})];
  }

  /* Slice-aware sections. Filters narrow the row sets via the cube; figures that
     are precomputed company-level scalars are swapped for cube-derived ones,
     because those scalars cannot be re-derived for a subset. */

  noMatch(){ return this.card("لا توجد نتائج",this.empty("لا توجد بيانات تطابق هذا التقسيم."),{k:"nm"}); }

  sliceKpis(R,RD,f){
    const s=R.applyFilters(RD,f);
    return this.kpiGridRepo([
      ["إيراد التقسيم", R.fmtEGP(s.sales), "حصة "+R.fmtPct(s.shareOfTotal), R.C.blue],
      ["عدد العملاء", R.fmt0(s.nCustomers), "من 337", R.C.indigo],
      ["الكمية", R.fmt0(s.qty), "", R.C.green],
      ["متوسط سعر البيع", R.fmtEGP(s.avgPrice), "إيراد ÷ كمية", R.C.pale]]);
  }

  repoCustomers(R,RD,f){
    const keep=R.matchingCustomerCodes(RD,f);
    const dimByCode=Object.fromEntries(RD.dim_customers.map(c=>[c.customer_code,c]));
    let cust=[...RD.customer_pareto].sort((a,b)=>b.line_total-a.line_total);
    let bonus=RD.customer_bonus_summary;
    if(keep){ cust=cust.filter(c=>keep.has(c.customer_code));
              bonus=bonus.filter(c=>keep.has(c.customer_code)); }
    if(!cust.length) return [this.noMatch()];

    const abcCounts={A:0,B:0,C:0}; cust.forEach(c=>{abcCounts[c.abc_class]=(abcCounts[c.abc_class]||0)+1;});
    /* Cumulative share is recomputed over the rows actually shown; the source
       cum_pct is cumulative over all 337 customers and reads as nonsense once
       the list is filtered. Unfiltered it reproduces the original values. */
    const total=cust.reduce((a,c)=>a+c.line_total,0); let run=0;
    const rows=cust.map(c=>{ run+=c.line_total; return {c, cum: total? run/total*100 : 0}; });

    return [
      R.isEmptyFilters(f)?this.kpiGridRepo(R.kpisCust(RD)):this.sliceKpis(R,RD,f),
      this.card("توزيع العملاء حسب فئة ABC",this.barsH([["فئة A",abcCounts.A||0,R.C.blue],["فئة B",abcCounts.B||0,R.C.amber],["فئة C",abcCounts.C||0,R.C.grey]],R.fmt0),{k:"u1",sub:R.isEmptyFilters(f)?null:"داخل التقسيم"}),
      this.card(R.isEmptyFilters(f)?"أعلى 25 عميلاً — التفصيل الكامل":"العملاء في التقسيم",this.rowsList(rows.slice(0,25),[["العميل",r=>r.c.customer_name],["الإيراد",r=>R.fmt0(r.c.line_total)],["% تراكمي",r=>R.fmt1(r.cum)+"%"],["ABC",r=>r.c.abc_class],["XYZ",r=>r.c.xyz_class||"—"],["المندوب",r=>(dimByCode[r.c.customer_code]||{}).rep||"—"],["رصيد المديونية",r=>{const b=(dimByCode[r.c.customer_code]||{}).ar_net_balance;return b==null?"—":R.fmt0(b);}]]),{k:"u2",sub:rows.length+" عميل"}),
      this.card("مبيعات كل عميل ونسبة البونص",this.rowsList(bonus,[["العميل",r=>r.customer_name],["إجمالي المبيعات",r=>R.fmt0(r.total_sales_egp)],["كمية البونص",r=>R.fmt0(r.bonus_qty)],["قيمة البونص",r=>R.fmt0(r.bonus_estimated_value_egp)],["% البونص",r=>R.fmt2(r.bonus_pct_of_sales_value)+"%"],["المندوب",r=>r.rep||"—"],["الفواتير",r=>R.fmt0(r.n_invoices)]]),{k:"u3",sub:bonus.length+" عميل"})];
  }

  repoDebt(R,RD,f){
    const keep=R.matchingCustomerCodes(RD,f);
    let balances=[...RD.ar_balances].sort((a,b)=>b.net_balance-a.net_balance);
    if(keep) balances=balances.filter(b=>keep.has(b.customer_code));

    /* Rep totals are re-summed from the filtered balances so the bars always
       match the list beneath them. */
    const repTot=new Map();
    for(const b of balances) repTot.set(b.rep,(repTot.get(b.rep)||0)+b.net_balance);
    const repBars=[...repTot.entries()].sort((a,b)=>b[1]-a[1]).map(([k,v])=>[k,v,R.C.indigo]);

    const kpis = R.isEmptyFilters(f) ? R.kpisDebt(RD) : [
      ["صافي رصيد المديونية", R.fmtEGP(balances.reduce((a,b)=>a+b.net_balance,0)), "لقطة 2026/7/4", R.C.amber],
      ["إجمالي مدين", R.fmtEGP(balances.reduce((a,b)=>a+b.debit,0)), "", R.C.red],
      ["إجمالي دائن", R.fmtEGP(balances.reduce((a,b)=>a+b.credit,0)), "", R.C.green],
      ["عدد العملاء", R.fmt0(balances.length), "في التقسيم", R.C.blue]];

    return [
      this.kpiGridRepo(kpis),
      this.card("رصيد المديونية حسب المندوب",repBars.length?this.barsH(repBars,R.fmtEGPk):this.empty("لا توجد بيانات"),{k:"d1",sub:"لقطة 2026/7/4"}),
      this.card("أرصدة العملاء",balances.length?this.rowsList(balances,[["العميل",r=>r.customer_name],["الرصيد الصافي",r=>R.fmt0(r.net_balance)],["مدين",r=>R.fmt0(r.debit)],["دائن",r=>R.fmt0(r.credit)],["المندوب",r=>r.rep||"—"],["الهاتف",r=>r.phone||"—"]]):this.empty("لا توجد بيانات"),{k:"d2",sub:balances.length+" عميل"})];
  }

  repoBrands(R,RD,f){
    const slice=R.applyFilters(RD,f);
    if(slice.isEmpty) return [this.noMatch()];
    const brands3=["الهنا","ابوهاشم","اسبشيال"];
    const shareRows = R.isEmptyFilters(f)
      ? [...RD.brand_summary].sort((a,b)=>b.revenue-a.revenue).map(b=>[b.brand,b.revenue,R.BRAND_COLORS[b.brand]||R.C.grey])
      : slice.byBrand.map(b=>[b.name,b.sales,R.BRAND_COLORS[b.name]||R.C.grey]);

    /* Per-brand monthly series survive a brand filter but not one that also
       narrows by rep, customer or item — there is no such cube. */
    const canTrend = !f.rep && !f.customerCode && !f.itemName;
    const trend = f.brand ? [f.brand] : brands3;
    const entries = trend.map(b=>[b, R.BRAND_COLORS[b]||R.C.grey,
      R.brandSeries(RD,b).map(v=>({v}))]);

    const kpis = R.isEmptyFilters(f) ? R.kpisBrands(RD)
      : slice.byBrand.map(b=>[b.name, R.fmtEGP(b.sales),
          R.fmtPct(slice.sales?b.sales/slice.sales*100:0)+" من التقسيم",
          R.BRAND_COLORS[b.name]||R.C.grey]);

    return [
      this.kpiGridRepo(kpis),
      this.card("حصة العلامات التجارية من إجمالي الإيراد",this.barsH(shareRows,R.fmtEGPk),{k:"br1",sub:R.isEmptyFilters(f)?null:"داخل التقسيم"}),
      this.card("الإيراد الشهري لكل علامة تجارية",canTrend?this.miniLines(entries):this.empty("التفصيل الشهري غير متاح لهذا التقسيم. المصدر يوفّر الإيراد الشهري على مستوى العلامة التجارية فقط."),{k:"br2"})];
  }

  repoProducts(R,RD,f){
    const slice=R.applyFilters(RD,f);
    if(slice.isEmpty) return [this.noMatch()];
    /* Sales come from the cube when sliced; ABC/XYZ stay the item's global
       classification, carried across by name. */
    const gl=Object.fromEntries(RD.item_abc_xyz.map(i=>[i.item_name_canonical,i]));
    let rows;
    if(R.isEmptyFilters(f)){
      const items=[...RD.item_abc_xyz].sort((a,b)=>b.line_total-a.line_total);
      const tot=items.reduce((a,i)=>a+i.line_total,0); let run=0;
      rows=items.map(i=>{ run+=i.line_total;
        return {name:i.item_name_canonical, sales:i.line_total, brand:i.brand,
                abc:i.abc_class, xyz:i.xyz_class||"—", cum: tot? run/tot*100 : 0}; });
    } else {
      let run=0;
      rows=slice.byItem.map(r=>{ run+=r.sales; const g=gl[r.name]||{};
        return {name:r.name, sales:r.sales, brand:g.brand||"—",
                abc:g.abc_class||"—", xyz:g.xyz_class||"—",
                cum: slice.sales? run/slice.sales*100 : 0}; });
    }
    return [
      R.isEmptyFilters(f)?this.kpiGridRepo(R.kpisProducts(RD)):this.sliceKpis(R,RD,f),
      this.card("أعلى 20 صنفًا بالإيراد",this.barsH(rows.slice(0,20).map(r=>[r.name,r.sales,R.C.green]),R.fmtEGPk),{k:"pr1",sub:R.isEmptyFilters(f)?null:"داخل التقسيم"}),
      this.card("أداء الأصناف — التفصيل",this.rowsList(rows.slice(0,30),[["الصنف",r=>r.name],["الإيراد",r=>R.fmt0(r.sales)],["% تراكمي",r=>R.fmt1(r.cum)+"%"],["ABC",r=>r.abc],["XYZ",r=>r.xyz],["العلامة",r=>r.brand]]),{k:"pr2",sub:rows.length+" صنف"})];
  }

  /* The interactive slice-and-dice section. */
  repoAnalysis(R,RD,f){
    const s=R.applyFilters(RD,f);
    if(s.isEmpty) return [this.card("لا توجد نتائج",this.empty("لا توجد بيانات تطابق هذا التقسيم. جرّب إزالة أحد الفلاتر."),{k:"an0"})];

    let monthly;
    if(s.monthlyAvailability==="company")
      monthly=this.card("الإيراد الشهري",this.lineChart(RD.monthly_series.map(m=>({v:m.revenue})),R.C.blue),{k:"an1",sub:"18 شهرًا"});
    else if(s.monthlyAvailability==="brand")
      monthly=this.card("الإيراد الشهري — "+f.brand,this.lineChart(R.brandSeries(RD,f.brand).map(v=>({v})),R.BRAND_COLORS[f.brand]||R.C.blue),{k:"an1",sub:"18 شهرًا"});
    else
      monthly=this.card("الإيراد الشهري",this.empty("التفصيل الشهري غير متاح لهذا التقسيم. المصدر يوفّر الإيراد الشهري على مستوى الشركة والعلامة التجارية فقط."),{k:"an1"});

    const cards=[
      this.kpiGridRepo([
        ["إيراد التقسيم", R.fmtEGP(s.sales), R.isEmptyFilters(f)?"كل الفترة":"من "+R.fmtEGP(s.grandTotal), R.C.blue],
        ["حصة من إجمالي الإيراد", R.fmtPct(s.shareOfTotal), "", R.C.orange],
        ["الكمية", R.fmt0(s.qty), "", R.C.green],
        ["متوسط سعر البيع", R.fmtEGP(s.avgPrice), "إيراد ÷ كمية", R.C.pale],
        ["عدد العملاء", R.fmt0(s.nCustomers), "من 337", R.C.indigo],
        ["عدد الأصناف", R.fmt0(s.nItems), "من 86", R.C.amber]]),
      monthly];

    /* A breakdown only informs when the filter has not already pinned it. */
    if(!f.rep && s.byRep.length>1)
      cards.push(this.card("حسب المندوب",this.barsH(s.byRep.map(r=>[r.name,r.sales,R.C.indigo]),R.fmtEGPk),{k:"an2",sub:String(s.byRep.length)}));
    if(!f.brand && s.byBrand.length>1)
      cards.push(this.card("حسب العلامة التجارية",this.barsH(s.byBrand.map(b=>[b.name,b.sales,R.BRAND_COLORS[b.name]||R.C.grey]),R.fmtEGPk),{k:"an3",sub:String(s.byBrand.length)}));
    if(!f.customerCode && s.byCustomer.length>1)
      cards.push(this.card("أعلى العملاء في هذا التقسيم",this.barsH(s.byCustomer.slice(0,15).map(c=>[c.name,c.sales,R.C.blue]),R.fmtEGPk),{k:"an4",sub:Math.min(15,s.byCustomer.length)+" من "+s.byCustomer.length}));
    if(!f.itemName && s.byItem.length>1)
      cards.push(this.card("أعلى الأصناف في هذا التقسيم",this.barsH(s.byItem.slice(0,15).map(i=>[i.name,i.sales,R.C.green]),R.fmtEGPk),{k:"an5",sub:Math.min(15,s.byItem.length)+" من "+s.byItem.length}));
    return cards;
  }

  repoForecast(R,RD){
    const fc=RD.forecast;
    const basePts=RD.monthly_series.map(m=>m.revenue).concat((fc.forecast_company_revenue||[]).map(r=>r.base_case)).map(v=>({v}));
    const cvRows=Object.entries(fc.cv_summary||{}).filter(([,v])=>v).sort((a,b)=>a[1].rmse-b[1].rmse).map(([name,v])=>({name,...v}));
    return [
      this.card("منهجية التوقع",React.createElement("div",{style:{fontSize:11.5,lineHeight:1.8,color:"#94a3b8"}},fc.method_note+" النموذج الفائز: "+fc.best_model_by_rolling_rmse+"."),{k:"fc0"}),
      this.card("توقع إيراد الشركة (فعلي + أساسي)",this.lineChart(basePts,R.C.orange),{k:"fc1"}),
      this.card("جدول التوقع الشهري (3 سيناريوهات)",this.rowsList(fc.forecast_company_revenue||[],[["الشهر",r=>R.monthAr(r.month)],["متحفظ",r=>R.fmt0(r.conservative_case)],["أساسي",r=>R.fmt0(r.base_case)],["متفائل",r=>R.fmt0(r.optimistic_case)]]),{k:"fc2"}),
      this.card("مقارنة نماذج التنبؤ (rolling CV)",this.rowsList(cvRows,[["النموذج",r=>r.name],["RMSE",r=>R.fmt0(r.rmse)],["MAE",r=>R.fmt0(r.mae)],["MAPE%",r=>R.fmt1(r.mape)],["SMAPE%",r=>R.fmt1(r.smape)]]),{k:"fc3",sub:"أقل RMSE = أفضل"})];
  }

  /* ---- الربحية ------------------------------------------------------------
     Built from window.DASH_MARGIN (analysis/13_join_cost_margin.py). Ignores
     the filter bar: margin comes from precomputed company-level aggregates and
     cannot honestly be re-derived for an arbitrary slice, exactly as with the
     fin / forecast / quality sections. */
  repoMargin(R,RD){
    if(!M.has()) return [this.empty("بيانات التكلفة غير محمّلة في هذا البناء.")];
    const d=M.D(), C=this.state.C, win=M.windowLabel(d);
    const ex=(d.meta.excluded_months||[]).length;

    const banner=React.createElement("div",{key:"mb",style:{padding:"11px 12px",borderRadius:12,
        background:"rgba(245,158,11,.10)",border:"1px solid rgba(245,158,11,.30)",
        fontSize:11,lineHeight:1.85,color:"#fcd9a0"}},
      "التكلفة مقيسة لشهر "+M.arMonth(d.meta.cost_month)+" فقط. النافذة الموثوقة هي "+win+
      " — وهي الشهور التي لا تبعد أسعارها عن شهر التكلفة بأكثر من "+
      d.meta.max_drift_pct+"%. ",
      React.createElement("br"),
      "استُبعد "+ex+" شهرًا سابقًا: كانت الأسعار أدنى بنحو 15% قبل زيادة مارس–أبريل 2026، "+
      "واحتساب تكلفة يونيو عليها يُظهر هامشًا سالبًا هو أثر منهجي لا خسارة فعلية.");

    const uncosted=(d.uncosted_items||[]).slice(0,8)
      .map(r=>[r.item_name||r.item_code, r.revenue, "#64748b"]);

    const gaps=M.pricingGap(d);

    return [
      banner,
      this.kpiGridRepo(M.kpisWindow(d,R)),
      this.card("الشهر المقيس — مطابق لقائمة الدخل",
        this.kpiGridRepo(M.kpisMeasured(d,R)),
        {k:"mm",sub:M.arMonth(d.meta.cost_month)}),
      this.chartCard("اتجاه الهامش ومؤشر الأسعار",M.trend(d,C),
        {k:"mt",h:C.H.tall,
         sub:"الرمادي: شهور خارج النافذة"}),
      this.card("هامش مجمل حسب العلامة التجارية",
        this.barsH(M.bars(d.by_brand||[],"brand",R),v=>R.fmtPct(v)),
        {k:"mbr",sub:win,approx:true}),
      this.card("هامش مجمل حسب المندوب",
        this.barsH(M.bars(d.by_rep||[],"rep",R,(d.totals.measured||{}).gross_margin_pct),
                   v=>R.fmtPct(v)),
        {k:"mrp",sub:win,approx:true}),
      this.chartCard("الإيراد مقابل الهامش لكل صنف",M.itemScatter(d,C),
        {k:"mis",h:C.H.tall,approx:true,
         sub:"أفقي: الإيراد · رأسي: هامش مجمل · حجم الفقاعة: الإيراد · "+win}),
      this.card("أصناف سعرها الفعلي دون السعر الموصى به",
        gaps.length?this.rowsList(gaps,[
            ["الصنف",r=>r.cost_item_name],
            ["السعر الفعلي",r=>R.fmt2(r.june_avg_price)],
            ["الموصى به",r=>R.fmt2(r.rec_price)],
            ["الفجوة",r=>R.fmtPct(r.gap_pct)],
            ["الحد الأدنى",r=>R.fmt2(r.floor_price)],
            ["فئة ABC",r=>r.abc],
            ["ملاحظة",r=>r.flags||"—"],
          ]):this.empty("لا توجد أصناف تحت السعر الموصى به."),
        {k:"mpg",sub:"من محرك التسعير في نموذج التكاليف"}),
      this.card("إيراد بلا بيانات تكلفة",
        this.barsH(uncosted,R.fmtEGPk),
        {k:"muc",sub:R.fmtPct(100-d.meta.coverage_pct)+" من الإيراد — لا تُحتسب له تكلفة صفرية"}),
    ];
  }

  /* ---- استخراج التقارير والرسوم ------------------------------------------
     The catalogue of tables the user can take away. Built from the dataset that
     is currently selected, so what leaves the app is what the app is showing.

     Filters are applied only on columns a row actually carries (rep, brand,
     customer). Anything the row cannot be filtered on is exported whole rather
     than half-filtered, and the sheet states the row count either way. */
  exportTables(){
    const st=this.state, num=v=>(v==null||v===""?null:Number(v));
    const col=(label,key,fn)=>({label, get:fn||(r=>r[key])});
    const out=[];

    const mf=(rows,pred)=>rows.filter(pred);

    if(st.src==="dash" && st.api){
      const D=st.api.D, f=st.filters||{};
      const inMonth=r=>!f.month||f.month==="all"||r.month===f.month;
      const byRep=r=>!f.rep||r.rep===f.rep;
      out.push(
        {id:"invoices", label:"الفواتير",
         rows:mf(D.invoices||[],r=>inMonth(r)&&byRep(r)), columns:[
          col("رقم الفاتورة","invoice_no"), col("التاريخ","invoice_date"),
          col("كود العميل","customer_code"), col("العميل","customer_name"),
          col("المندوب","rep"), col("القيمة",null,r=>num(r.reported_total)),
          col("المسدد",null,r=>num(r.paid)), col("المتبقي",null,r=>num(r.remaining)),
          col("الكمية",null,r=>num(r.qty_total)), col("عدد البنود",null,r=>num(r.n_lines)),
          col("الحالة","status")]},
        {id:"lines", label:"بنود الفواتير",
         rows:mf(D.lines||[],r=>inMonth(r)&&byRep(r)), columns:[
          col("رقم الفاتورة","invoice_no"), col("التاريخ","invoice_date"),
          col("العميل","customer_name"), col("المندوب","rep"),
          col("كود الصنف","item_code"), col("الصنف","item_name"),
          col("العلامة","brand"), col("الكمية",null,r=>num(r.qty)),
          col("سعر الوحدة",null,r=>num(r.unit_price)),
          col("الإجمالي",null,r=>num(r.line_total)),
          col("كراتين",null,r=>num(r.boxes)), col("بونص",null,r=>r.is_bonus?"نعم":"لا")]},
        {id:"receivables", label:"أرصدة المديونية",
         rows:mf(((D.receivables||{}).rows)||[],byRep), columns:[
          col("كود العميل","customer_code"), col("العميل","customer_name"),
          col("المندوب","rep"), col("الرصيد",null,r=>num(r.balance!=null?r.balance:r.net_balance)),
          col("متأخر",null,r=>num(r.overdue)), col("جاري",null,r=>num(r.current))]},
        {id:"collections", label:"التحصيلات",
         rows:((D.collections||{}).receipts)||[], columns:[
          col("التاريخ","date"), col("كود العميل","customer_code"),
          col("العميل","customer_name"), col("المندوب","rep"),
          col("المبلغ",null,r=>num(r.amount)), col("الوسيلة","method")]},
        {id:"returns", label:"المرتجعات",
         rows:((D.collections||{}).returns_rows)||[], columns:[
          col("التاريخ","date"), col("كود العميل","customer_code"),
          col("العميل","customer_name"), col("القيمة",null,r=>num(r.amount))]},
        {id:"monthly", label:"الملخص الشهري", rows:D.monthly||[], columns:[
          col("الشهر","month"), col("صافي المبيعات",null,r=>num(r.net_sales)),
          col("الفواتير",null,r=>num(r.invoices)), col("العملاء",null,r=>num(r.customers)),
          col("الكمية",null,r=>num(r.qty))]});

      try{
        const rows=AG.agingRows(D);
        out.push({id:"aging", label:"أعمار المديونية",
          rows:mf(rows,byRep), columns:[
            col("كود العميل","code"), col("العميل","name"), col("المندوب","rep"),
            col("الرصيد",null,r=>num(r.balance))].concat(
            AG.AGE_TIERS.map(t=>col(t.label,null,r=>num((r.tiers||{})[t.key]))))
            .concat([col("رصيد افتتاحي",null,r=>num(r.opening))])});
      }catch(e){}
    }

    const RD=st.RD;
    if(st.src!=="dash" && RD){
      const f=st.rf||{};
      const okRep=r=>!f.rep||r.rep===f.rep;
      const okBrand=r=>!f.brand||r.brand===f.brand;
      const okCust=r=>!f.customerCode||String(r.customer_code)===String(f.customerCode);
      out.push(
        {id:"customers", label:"العملاء",
         rows:mf(RD.dim_customers||[],r=>okRep(r)&&okCust(r)), columns:[
          col("الكود","customer_code"), col("العميل","customer_name"),
          col("المندوب","rep"), col("المدينة","city"),
          col("الإيراد",null,r=>num(r.total_revenue)),
          col("عدد الفواتير",null,r=>num(r.n_invoices)),
          col("أول فاتورة","first_invoice_date"), col("آخر فاتورة","last_invoice_date")]},
        {id:"ar", label:"أرصدة المديونية",
         rows:mf(RD.ar_balances||[],r=>okRep(r)&&okCust(r)), columns:[
          col("المندوب","rep"), col("الكود","customer_code"),
          col("العميل","customer_name"), col("المدينة","city"),
          col("مدين",null,r=>num(r.debit)), col("دائن",null,r=>num(r.credit)),
          col("صافي الرصيد",null,r=>num(r.net_balance))]},
        {id:"items", label:"الأصناف",
         rows:mf(RD.item_asp_boxes||[],okBrand), columns:[
          col("الكود","item_code"), col("الصنف","item_name"), col("العلامة","brand"),
          col("الكمية",null,r=>num(r.total_qty)),
          col("الإيراد",null,r=>num(r.total_revenue)),
          col("متوسط السعر",null,r=>num(r.asp_egp)),
          col("سعة الكرتونة","carton_capacity"),
          col("كراتين",null,r=>num(r.qty_in_boxes))]},
        {id:"brands", label:"العلامات التجارية",
         rows:mf(RD.brand_summary||[],okBrand), columns:[
          col("العلامة","brand"), col("الإيراد",null,r=>num(r.revenue)),
          col("الكمية",null,r=>num(r.qty)), col("العملاء",null,r=>num(r.n_customers)),
          col("الحصة %",null,r=>num(r.revenue_share_pct))]},
        {id:"monthly", label:"الملخص الشهري", rows:RD.monthly_series||[], columns:[
          col("الشهر","month"), col("الإيراد",null,r=>num(r.revenue)),
          col("الكمية",null,r=>num(r.qty)), col("الفواتير",null,r=>num(r.n_invoices)),
          col("العملاء",null,r=>num(r.n_customers)),
          col("متوسط السعر",null,r=>num(r.avg_selling_price)),
          col("نمو شهري %",null,r=>num(r.mom_growth_pct))]},
        {id:"bonus", label:"البونص لكل عميل",
         rows:mf(RD.customer_bonus_summary||[],r=>okRep(r)&&okCust(r)), columns:[
          col("الكود","customer_code"), col("العميل","customer_name"),
          col("المندوب","rep"), col("المبيعات",null,r=>num(r.total_sales_egp)),
          col("كمية البونص",null,r=>num(r.bonus_qty)),
          col("قيمة البونص",null,r=>num(r.bonus_estimated_value_egp)),
          col("% من الكمية",null,r=>num(r.bonus_pct_of_qty))]});
    }

    /* Profitability travels with either dataset: it is company-level and does
       not belong to one of them. Every label says تقديري where the figure is,
       so the caveat survives leaving the app. */
    if(M.has()){
      const d=M.D(), win=M.windowLabel(d);
      const mg=[col("هامش مجمل %",null,r=>num(r.gross_margin_pct)),
                col("هامش تشغيلي %",null,r=>num(r.op_margin_pct))];
      out.push(
        {id:"m_item", label:"الربحية — الأصناف ("+win+")", rows:d.by_item||[], columns:[
          col("الكود","item_code"), col("الصنف","item_name"), col("العلامة","brand"),
          col("الإيراد المُسعَّر",null,r=>num(r.revenue_costed)),
          col("مجمل الربح",null,r=>num(r.gross_profit)),
          col("الربح التشغيلي",null,r=>num(r.op_profit))].concat(mg)},
        {id:"m_cust", label:"الربحية — العملاء ("+win+")", rows:d.by_customer||[], columns:[
          col("الكود","customer_code"), col("العميل","customer_name"),
          col("المندوب","rep"), col("الإيراد",null,r=>num(r.revenue_total)),
          col("الإيراد المُسعَّر",null,r=>num(r.revenue_costed)),
          col("مجمل الربح",null,r=>num(r.gross_profit)),
          col("الربح التشغيلي",null,r=>num(r.op_profit))].concat(mg)},
        {id:"m_rep", label:"الربحية — المناديب ("+win+")", rows:d.by_rep||[], columns:[
          col("المندوب","rep"), col("الإيراد",null,r=>num(r.revenue_total)),
          col("الإيراد المُسعَّر",null,r=>num(r.revenue_costed)),
          col("مجمل الربح",null,r=>num(r.gross_profit)),
          col("الربح التشغيلي",null,r=>num(r.op_profit))].concat(mg)},
        {id:"m_month", label:"الربحية — الشهور", rows:d.by_month||[], columns:[
          col("الشهر","month"), col("الأساس",null,r=>r.basis==="measured"?"مقيس":"تقديري"),
          col("الإيراد المُسعَّر",null,r=>num(r.revenue_costed)),
          col("مجمل الربح",null,r=>num(r.gross_profit)),
          col("الربح التشغيلي",null,r=>num(r.op_profit))].concat(mg).concat([
          col("مؤشر الأسعار",null,r=>num(r.price_index)),
          col("انحراف عن شهر التكلفة %",null,r=>num(r.cost_period_drift_pct)),
          col("ضمن النافذة الموثوقة",null,r=>r.indicative_reliable?"نعم":"لا")])},
        {id:"m_price", label:"فجوة التسعير", rows:d.pricing_gap||[], columns:[
          col("الكود","item_code"), col("الصنف","cost_item_name"),
          col("العلامة","cost_brand"),
          col("السعر الفعلي",null,r=>num(r.june_avg_price)),
          col("الموصى به",null,r=>num(r.rec_price)),
          col("الحد الأدنى",null,r=>num(r.floor_price)),
          col("الفجوة %",null,r=>num(r.gap_pct)),
          col("فئة ABC","abc"), col("ملاحظة","flags")]});
    }
    return out.filter(t=>t.rows && t.rows.length);
  }

  exportSheet(){
    const st=this.state, tables=this.exportTables(), chartList=X.charts();
    const say=p=>Promise.resolve(p).then(m=>this.setState({xMsg:m}))
                                   .catch(e=>this.setState({xMsg:"تعذّر التصدير: "+e.message}));
    const H=(t,n)=>React.createElement("div",{key:"h"+t,style:{fontSize:11,fontWeight:700,
        color:"#94a3b8",marginTop:4,display:"flex",justifyContent:"space-between"}},
      React.createElement("span",null,t),
      n!=null?React.createElement("span",{style:{color:"#475569",fontWeight:400}},n):null);
    const btn=(lab,fn,accent)=>React.createElement("span",{key:lab,onClick:fn,
      style:{flex:"none",padding:"6px 11px",borderRadius:9,fontSize:11,cursor:"pointer",
        background:accent?"rgba(59,130,246,.16)":"rgba(255,255,255,.04)",
        border:"1px solid "+(accent?"rgba(59,130,246,.42)":"rgba(255,255,255,.10)"),
        color:accent?"#93c5fd":"#cbd5e1",whiteSpace:"nowrap"}},lab);
    const row=(label,sub,actions)=>React.createElement("div",{key:label,
      style:{display:"flex",alignItems:"center",gap:8,padding:"9px 10px",borderRadius:11,
        background:"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.07)"}},
      React.createElement("div",{style:{flex:1,minWidth:0,display:"flex",flexDirection:"column",gap:2}},
        React.createElement("span",{style:{fontSize:12,color:"#e2e8f0",overflow:"hidden",
          whiteSpace:"nowrap",textOverflow:"ellipsis"}},label),
        sub?React.createElement("span",{style:{fontSize:9.5,color:"#64748b"}},sub):null),
      React.createElement("div",{style:{display:"flex",gap:6,flex:"none"}},actions));

    const inner=[];
    inner.push(React.createElement("div",{key:"t",style:{fontSize:13.5,fontWeight:800,
      color:"#e2e8f0"}},"استخراج التقارير والرسوم"));
    inner.push(React.createElement("div",{key:"n",style:{fontSize:10.5,color:"#64748b",
      lineHeight:1.75}},"كل التصدير يتم على الجهاز — لا يُرسل أي شيء عبر الإنترنت."));

    if(st.xMsg) inner.push(React.createElement("div",{key:"msg",style:{padding:"8px 10px",
      borderRadius:10,background:"rgba(16,185,129,.12)",border:"1px solid rgba(16,185,129,.3)",
      fontSize:11,color:"#6ee7b7"}},st.xMsg));

    inner.push(H("تقرير كامل"));
    inner.push(row("كل الجداول في ملف Excel واحد",
      tables.length+" ورقة",[btn("Excel",()=>say(X.downloadXLSX(tables,"أبوهاشم-تقرير")),true)]));
    inner.push(row("التقرير المعروض كـ PDF","عبر نافذة الطباعة — العربية مُشكَّلة صحيحة",
      [btn("PDF",()=>{this.setState({sheet:null});say(X.printReport());},true)]));

    inner.push(H("الجداول",tables.length));
    tables.forEach(t=>inner.push(row(t.label,t.rows.length+" صف · "+t.columns.length+" عمود",
      [btn("CSV",()=>say(X.downloadCSV(t))),
       btn("Excel",()=>say(X.downloadXLSX([t],t.label)))])));

    inner.push(H("الرسوم البيانية",chartList.length));
    if(!chartList.length)
      inner.push(React.createElement("div",{key:"nc",style:{fontSize:11,color:"#64748b",
        padding:"8px 2px"}},"افتح قسمًا يحتوي رسومًا ثم أعد فتح هذه النافذة."));
    chartList.forEach(c=>inner.push(row(c.title,null,
      [btn("PNG",()=>say(X.downloadChartPNG(c))),
       btn("SVG",()=>say(X.downloadChartSVG(c)))])));

    return React.createElement("div",{onClick:()=>this.setState({sheet:null,xMsg:null}),
        style:{position:"absolute",inset:0,zIndex:9,background:"rgba(3,6,14,.7)",
          display:"flex",alignItems:"flex-end"}},
      React.createElement("div",{onClick:e=>e.stopPropagation(),
        style:{width:"100%",maxHeight:"86%",overflow:"auto",background:"#111827",
          borderTop:"1px solid rgba(255,255,255,.10)",borderRadius:"22px 22px 0 0",
          padding:"14px 14px 26px",display:"flex",flexDirection:"column",gap:9}},
        [React.createElement("div",{key:"g",style:{width:38,height:4,borderRadius:99,
          background:"rgba(255,255,255,.2)",margin:"0 auto 6px",flex:"none"}})].concat(inner)));
  }

  exportBtn(){
    return React.createElement("span",{onClick:()=>this.setState({sheet:"export",xMsg:null}),
      style:{position:"relative",width:34,height:34,flex:"none",borderRadius:10,
        background:"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.08)",
        display:"grid",placeItems:"center",color:"#e2e8f0",cursor:"pointer"},
      dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:17px;height:17px;'
        +'fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round">'
        +'<path d="M12 3v12M8 11l4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>'}});
  }

  repoQuality(R,RD){
    const dq=RD.data_quality;
    const missing=Object.entries(dq.missing_values||{}).map(([k,v])=>({field:k,...v}));
    return [
      this.kpiGridRepo(R.kpisQuality(RD)),
      this.card("القيم المفقودة حسب الحقل",this.rowsList(missing,[["الحقل",r=>r.field],["عدد المفقود",r=>R.fmt0(r.n_missing)],["%",r=>R.fmt2(r.pct_missing)+"%"]]),{k:"q1"}),
      this.card("عملاء لديهم رصيد مديونية بدون فواتير مطابقة",this.rowsList(RD.ar_zero_invoice_customers||[],[["العميل",r=>r.customer_name],["المندوب",r=>r.rep],["صافي الرصيد",r=>R.fmt0(r.net_balance)]]),{k:"q2",sub:(RD.ar_zero_invoice_customers||[]).length+" عميل"})];
  }

  /* Two-level filter sheet: dimension list, then a searchable option picker —
     needed because the customer list is 337 long and items 86. */
  rfSheet(R,RD){
    const st=this.state;
    if(!st.rfOpts) return null;
    const DIMS=[["rep","المندوب","reps",false],
                ["brand","العلامة التجارية","brands",false],
                ["customerCode","العميل","customers",true],
                ["itemName","الصنف","items",false]];

    const pick=(key,useCode,val)=>this.setState(p=>({rf:{...p.rf,[key]:val}, sheet:"rfilters", rfPick:null, rfQ:""}));

    // level 2 — options for one dimension
    if(st.rfPick){
      const d=DIMS.find(x=>x[0]===st.rfPick);
      const opts=st.rfOpts[d[2]]||[];
      const q=(st.rfQ||"").trim();
      const list=q?opts.filter(o=>o.name.indexOf(q)!==-1):opts;
      const cur=st.rf[d[0]];
      const row=(label,val,trailing,selected)=>React.createElement("div",{key:String(val)+label,
        onClick:()=>pick(d[0],d[3],val),
        style:{display:"flex",alignItems:"center",gap:8,padding:"11px 12px",marginBottom:6,borderRadius:10,cursor:"pointer",
               background:selected?"rgba(42,120,214,.14)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.07)"}},
        React.createElement("span",{style:{flex:1,minWidth:0,fontSize:12.5,color:selected?"#93c5fd":"#e2e8f0",fontWeight:selected?700:400,overflow:"hidden",whiteSpace:"nowrap",textOverflow:"ellipsis"}},label),
        trailing?React.createElement("span",{style:{fontSize:9.5,color:"#64748b",flex:"none"}},trailing):null);
      return [
        React.createElement("div",{key:"h",style:{display:"flex",alignItems:"center",gap:8,marginBottom:10}},
          React.createElement("span",{onClick:()=>this.setState({rfPick:null,rfQ:""}),style:{fontSize:12,color:"#93c5fd",cursor:"pointer"}},"‹ رجوع"),
          React.createElement("b",{style:{fontSize:14,color:"#e2e8f0"}},d[1]),
          React.createElement("span",{style:{marginInlineStart:"auto",fontSize:11,color:"#64748b"}},String(list.length))),
        opts.length>12?React.createElement("input",{key:"q",value:st.rfQ||"",placeholder:"بحث…",
          onChange:e=>this.setState({rfQ:e.target.value}),
          style:{width:"100%",marginBottom:10,padding:"9px 11px",borderRadius:10,background:"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.08)",color:"#e2e8f0",fontSize:12.5,fontFamily:"inherit",boxSizing:"border-box"}}):null,
        React.createElement("div",{key:"l"},
          [row("الكل",null,null,cur==null)].concat(
            list.slice(0,300).map(o=>row(o.name, d[3]?o.code:o.name, R.fmtEGPk(o.sales), (d[3]?o.code:o.name)===cur))))];
    }

    // level 1 — the four dimensions and their current values
    const label=(key,listKey,useCode)=>{
      const v=st.rf[key]; if(!v) return "الكل";
      if(!useCode) return v;
      const hit=(st.rfOpts[listKey]||[]).find(c=>c.code===v); return hit?hit.name:v;
    };
    return [
      React.createElement("div",{key:"h",style:{display:"flex",alignItems:"center",marginBottom:10}},
        React.createElement("b",{style:{fontSize:14,color:"#e2e8f0"}},"تصفية البيانات"),
        R.isEmptyFilters(st.rf)?null:React.createElement("span",{onClick:()=>this.setState({rf:{...R.EMPTY_FILTERS}}),
          style:{marginInlineStart:"auto",fontSize:11.5,color:"#e34948",cursor:"pointer"}},"مسح الكل")),
      React.createElement("div",{key:"d"},DIMS.map(([key,lab,listKey,useCode])=>{
        const v=label(key,listKey,useCode), on=v!=="الكل";
        return React.createElement("div",{key:key,onClick:()=>this.setState({rfPick:key,rfQ:""}),
          style:{display:"flex",alignItems:"center",gap:10,padding:"12px 13px",marginBottom:8,borderRadius:12,cursor:"pointer",
                 background:on?"rgba(42,120,214,.12)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.07)"}},
          React.createElement("span",{style:{fontSize:12,color:"#64748b",flex:"none"}},lab),
          React.createElement("span",{style:{flex:1,minWidth:0,textAlign:"end",fontSize:13,fontWeight:700,color:on?"#93c5fd":"#e2e8f0",overflow:"hidden",whiteSpace:"nowrap",textOverflow:"ellipsis"}},v),
          React.createElement("span",{style:{fontSize:14,color:"#64748b",flex:"none"}},"‹"));
      })),
      React.createElement("div",{key:"n",style:{fontSize:10.5,lineHeight:1.6,color:"#64748b",marginTop:2}},
        "الشهر غير متاح كعامل تصفية: لا توجد بيانات شهرية على مستوى العميل أو المندوب أو الصنف في المصدر.")];
  }

  buildRepo(){
    const st=this.state, R=st.R, RD=st.RD, T=st.T;
    const SEC=R.SECTIONS.concat(M.has()?[M.SECTION]:[]);
    const cur=SEC.find(s=>s.id===st.section)||SEC[0];
    const NAV=[["fin","المالية"],["sales","المبيعات"],["customers","العملاء"],["debt","المديونية"]];
    const moreIds=["brands","products","margin","forecast","quality","analysis"];

    const navEl=React.createElement("div",{style:{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:2}},
      NAV.map(([id,lab])=>{const on=st.section===id;
        return React.createElement("div",{key:id,onClick:()=>this.setState({section:id,sheet:null}),style:{display:"flex",flexDirection:"column",alignItems:"center",gap:4,padding:"6px 0",borderRadius:12,cursor:"pointer",background:on?"rgba(59,130,246,.12)":"transparent",color:on?"#93c5fd":"#64748b"}},
          React.createElement("span",{style:{width:19,height:19,display:"block"},dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round">'+T.KPI_ICONS[id==="fin"?"money":id==="sales"?"sales":id==="customers"?"users":"warn"]+'</svg>'}}),
          React.createElement("span",{style:{fontSize:9.5,fontWeight:on?700:400}},lab));})
      .concat([React.createElement("div",{key:"more",onClick:()=>this.setState({sheet:"nav"}),style:{display:"flex",flexDirection:"column",alignItems:"center",gap:4,padding:"6px 0",borderRadius:12,cursor:"pointer",color:moreIds.includes(st.section)?"#93c5fd":"#64748b"}},
        React.createElement("span",{style:{fontSize:17,lineHeight:"19px"}},"⋯"),
        React.createElement("span",{style:{fontSize:9.5}},"المزيد"))]));

    const srcEl = this.srcSwitch();
    const nActive=R.activeFilterCount(st.rf);
    const filterBtnEl=React.createElement("span",{onClick:()=>this.setState({sheet:"rfilters"}),style:{position:"relative",width:34,height:34,flex:"none",borderRadius:10,background:nActive?"rgba(42,120,214,.16)":"rgba(255,255,255,.03)",border:"1px solid "+(nActive?"rgba(42,120,214,.45)":"rgba(255,255,255,.08)"),display:"grid",placeItems:"center",color:nActive?"#93c5fd":"#e2e8f0",cursor:"pointer"}},
      React.createElement("span",{key:"i",style:{display:"block",width:17,height:17},dangerouslySetInnerHTML:{__html:'<svg viewBox="0 0 24 24" style="width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>'}}),
      nActive?React.createElement("span",{key:"b",style:{position:"absolute",top:-4,insetInlineEnd:-4,minWidth:14,height:14,padding:"0 3px",borderRadius:99,background:"#2a78d6",color:"#fff",fontSize:9,fontWeight:800,lineHeight:"14px",textAlign:"center"}},String(nActive)):null);

    /* Chips: section title, period, then one removable chip per active
       dimension. Customer is filtered by code, so resolve the name back. */
    const custName=code=>{ const o=(st.rfOpts&&st.rfOpts.customers)||[];
      const hit=o.find(c=>c.code===code); return hit?hit.name:code; };
    const chipDefs=[];
    if(st.rf.rep) chipDefs.push(["rep","المندوب",st.rf.rep]);
    if(st.rf.brand) chipDefs.push(["brand","العلامة",st.rf.brand]);
    if(st.rf.customerCode) chipDefs.push(["customerCode","العميل",custName(st.rf.customerCode)]);
    if(st.rf.itemName) chipDefs.push(["itemName","الصنف",st.rf.itemName]);

    const chipsEl=React.createElement("div",{style:{flex:"none",position:"relative",display:"flex",alignItems:"center",gap:6,padding:"8px 13px",overflowX:"auto",borderBottom:"1px solid rgba(255,255,255,.06)"}},
      [React.createElement("span",{key:"h2",style:{fontSize:12,fontWeight:700,color:"#e2e8f0",flex:"none",whiteSpace:"nowrap"}},cur.title),
       React.createElement("span",{key:"p",style:{flex:"none",fontSize:10.5,padding:"4px 9px",borderRadius:99,background:"rgba(59,130,246,.14)",border:"1px solid rgba(59,130,246,.3)",color:"#93c5fd",whiteSpace:"nowrap"}},
         /* الربحية covers only the months that pass the price-drift gate, so it
            must not wear the dataset-wide period chip. */
         st.section==="margin"&&M.has() ? M.windowLabel(M.D())
                                        : RD.financial.period.start+" — "+RD.financial.period.end)]
      .concat(chipDefs.map(([k,lab,val])=>React.createElement("span",{key:k,
        onClick:()=>this.setState(p=>({rf:{...p.rf,[k]:null}})),
        style:{flex:"none",fontSize:10.5,padding:"4px 9px",borderRadius:99,background:"rgba(227,73,72,.14)",border:"1px solid rgba(227,73,72,.28)",color:"#fca5a5",cursor:"pointer",whiteSpace:"nowrap",maxWidth:190,overflow:"hidden",textOverflow:"ellipsis"}},
        lab+": "+val+"  ✕"))));

    /* fin / forecast / quality are built from precomputed company-level
       scalars, so they render unfiltered under a notice rather than pretending
       a filter applied. */
    /* margin joins precomputed company-level cost aggregates, so like
       fin / forecast / quality it cannot be re-derived for a slice. */
    const unfilterable=R.UNFILTERABLE.concat(["margin"]).includes(st.section);
    const f=unfilterable?R.EMPTY_FILTERS:st.rf;

    let body;
    if(st.section==="fin") body=this.repoFin(R,RD);
    else if(st.section==="sales") body=this.repoSales(R,RD);
    else if(st.section==="customers") body=this.repoCustomers(R,RD,f);
    else if(st.section==="debt") body=this.repoDebt(R,RD,f);
    else if(st.section==="brands") body=this.repoBrands(R,RD,f);
    else if(st.section==="products") body=this.repoProducts(R,RD,f);
    else if(st.section==="forecast") body=this.repoForecast(R,RD);
    else if(st.section==="analysis") body=this.repoAnalysis(R,RD,f);
    else if(st.section==="margin") body=this.repoMargin(R,RD);
    else body=this.repoQuality(R,RD);

    const head=[React.createElement("div",{key:"sub",style:{fontSize:11,color:"#64748b",lineHeight:1.7}},cur.sub)];
    if(unfilterable && !R.isEmptyFilters(st.rf))
      head.push(React.createElement("div",{key:"nf",style:{padding:"10px 12px",borderRadius:12,background:"rgba(237,161,0,.10)",border:"1px solid rgba(237,161,0,.30)",fontSize:11,lineHeight:1.7,color:"#fcd34d"}},
        "الفلاتر لا تنطبق على هذا القسم — أرقامه محسوبة مسبقًا على مستوى الشركة ولا يمكن إعادة اشتقاقها لتقسيم جزئي. الأرقام أدناه للفترة كاملة."));
    body=head.concat(body);

    let sheetEl=null;
    if(st.sheet==="export"){
      sheetEl=this.exportSheet();
    } else if(st.sheet==="rfilters"){
      const inner=this.rfSheet(R,RD);
      sheetEl=React.createElement("div",{onClick:()=>this.setState({sheet:null,rfPick:null,rfQ:""}),style:{position:"absolute",inset:0,zIndex:9,background:"rgba(3,6,14,.7)",display:"flex",alignItems:"flex-end"}},
        React.createElement("div",{onClick:e=>e.stopPropagation(),style:{width:"100%",maxHeight:"82%",overflow:"auto",background:"#111827",borderTop:"1px solid rgba(255,255,255,.10)",borderRadius:"22px 22px 0 0",padding:"14px 14px 26px",display:"flex",flexDirection:"column"}},
          [React.createElement("div",{key:"g",style:{width:38,height:4,borderRadius:99,background:"rgba(255,255,255,.2)",margin:"0 auto 10px",flex:"none"}})].concat(inner||[])));
    } else if(st.sheet==="nav"){
      sheetEl=React.createElement("div",{onClick:()=>this.setState({sheet:null}),style:{position:"absolute",inset:0,zIndex:9,background:"rgba(3,6,14,.7)",display:"flex",alignItems:"flex-end"}},
        React.createElement("div",{onClick:e=>e.stopPropagation(),style:{width:"100%",maxHeight:"78%",overflow:"auto",background:"#111827",borderTop:"1px solid rgba(255,255,255,.10)",borderRadius:"22px 22px 0 0",padding:"14px 14px 26px",display:"flex",flexDirection:"column",gap:9}},
          [React.createElement("div",{key:"g",style:{width:38,height:4,borderRadius:99,background:"rgba(255,255,255,.2)",margin:"0 auto 6px"}})]
          .concat(SEC.map(s=>React.createElement("div",{key:s.id,onClick:()=>this.setState({section:s.id,sheet:null}),style:{padding:"12px 13px",borderRadius:12,background:st.section===s.id?"rgba(59,130,246,.12)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.07)",fontSize:13,color:"#e2e8f0",cursor:"pointer"}},s.label)))));
    } else if(st.sheet){
      const inner=[React.createElement("div",{key:"d",style:{display:"flex",flexDirection:"column"}},
        st.sheet.cols.map((c,i)=>React.createElement("div",{key:i,style:{display:"flex",justifyContent:"space-between",gap:12,padding:"8px 0",borderBottom:"1px solid rgba(255,255,255,.06)",fontSize:12}},
          React.createElement("span",{style:{color:"#64748b"}},c[0]),
          React.createElement("b",{style:{color:"#e2e8f0",fontFamily:"'JetBrains Mono',monospace"}},String(c[1](st.sheet.r)??"—")))))];
      sheetEl=React.createElement("div",{onClick:()=>this.setState({sheet:null}),style:{position:"absolute",inset:0,zIndex:9,background:"rgba(3,6,14,.7)",display:"flex",alignItems:"flex-end"}},
        React.createElement("div",{onClick:e=>e.stopPropagation(),style:{width:"100%",maxHeight:"78%",overflow:"auto",background:"#111827",borderTop:"1px solid rgba(255,255,255,.10)",borderRadius:"22px 22px 0 0",padding:"14px 14px 26px",display:"flex",flexDirection:"column",gap:9}},
          [React.createElement("div",{key:"g",style:{width:38,height:4,borderRadius:99,background:"rgba(255,255,255,.2)",margin:"0 auto 6px"}})].concat(inner)));
    }

    const dq=RD.data_quality||{};
    const statusEl=React.createElement("div",null,
      React.createElement("b",{style:{color:"#10b981"}},"window.DASH_DATA متصل"),
      React.createElement("div",{style:{marginTop:6,lineHeight:1.9}},
        "الفترة: "+RD.financial.period.start+" → "+RD.financial.period.end,
        React.createElement("br"),
        "فواتير: "+R.fmt0(dq.n_invoices)+" · بنود: "+R.fmt0(dq.n_rows)+" · عملاء: "+R.fmt0(RD.eda_summary.n_customers)+" · علامات: "+R.fmt0(RD.eda_summary.n_brands)));

    const sectionListEl=React.createElement("div",{dir:"rtl",style:{display:"flex",flexWrap:"wrap",gap:6}},
      SEC.map(s=>React.createElement("span",{key:s.id,onClick:()=>this.setState({section:s.id}),style:{fontSize:11,padding:"5px 10px",borderRadius:99,cursor:"pointer",background:st.section===s.id?"rgba(59,130,246,.16)":"rgba(255,255,255,.03)",border:"1px solid rgba(255,255,255,.08)",color:"#cbd5e1"}},s.label)));

    return {bodyEl:body, navEl, chipsEl, filterBarEl:null, srcEl, filterBtnEl,
            exportBtnEl:this.exportBtn(), sheetEl, statusEl, sectionListEl};
  }

  render(){
    const v=this.renderVals();
    return React.createElement("div",{dir:"rtl","data-print":"app",style:{height:"100dvh",width:"100%",maxWidth:480,margin:"0 auto",background:"#0a0e1a",color:"#e2e8f0",fontFamily:"'Cairo',system-ui,'Segoe UI',Tahoma,sans-serif",position:"relative",display:"flex",flexDirection:"column",overflow:"hidden"}},
      React.createElement("div",{"data-print":"backdrop",style:{position:"absolute",inset:0,background:"radial-gradient(600px 300px at 100% -10%,rgba(59,130,246,.10),transparent 60%),radial-gradient(500px 250px at -10% 8%,rgba(139,92,246,.10),transparent 55%)",pointerEvents:"none"}}),
      React.createElement("div",{style:{flex:"none",position:"relative",display:"flex",alignItems:"center",gap:11,padding:"12px 14px 12px",borderBottom:"1px solid rgba(255,255,255,.08)",background:"rgba(17,24,39,.85)"}},
        React.createElement("span",{style:{width:40,height:40,flex:"none",borderRadius:12,background:"linear-gradient(135deg,#3b82f6,#8b5cf6)",display:"grid",placeItems:"center",fontWeight:800,fontSize:14,color:"#fff"}},"أه"),
        React.createElement("div",{style:{flex:1,minWidth:0,display:"flex",flexDirection:"column",gap:2}},
          React.createElement("span",{style:{fontSize:13.5,fontWeight:800,color:"#e2e8f0",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}},"أبو هاشم للحوم — Food Industries"),
          React.createElement("span",{style:{fontSize:11,color:"#94a3b8"}},"لوحة الأداء التنفيذي المالي")),
        React.createElement("div",{"data-print":"actions",style:{display:"flex",gap:7,flex:"none"}},
          v.exportBtnEl||null, v.filterBtnEl)),
      v.srcEl,
      v.chipsEl,
      v.filterBarEl,
      React.createElement("div",{"data-print":"scroll",style:{flex:1,minHeight:0,overflow:"auto",position:"relative",padding:"12px 13px 18px",display:"flex",flexDirection:"column",gap:11}},
        v.bodyEl),
      v.sheetEl,
      React.createElement("div",{"data-print":"nav",style:{flex:"none",position:"relative",borderTop:"1px solid rgba(255,255,255,.08)",background:"rgba(13,18,32,.96)",padding:"7px 5px 20px"}},
        v.navEl));
  }
}

window.__C = C;
(function(){
  var root = document.getElementById("root");
  if (ReactDOM.createRoot) ReactDOM.createRoot(root).render(React.createElement(App));
  else ReactDOM.render(React.createElement(App), root);
})();

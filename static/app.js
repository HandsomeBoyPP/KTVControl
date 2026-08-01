// ================================================================



// KTV 前台控制 - App Logic v5



// ================================================================







const API = {



  rooms: "/api/rooms", roomStatus: "/api/rooms/status",



  open: "/api/rooms/open", close: "/api/rooms/close", extend: "/api/rooms/extend",



  bookings: "/api/bookings",



  members: "/api/members", memberVerify: "/api/members/verify",



  recharge: "/api/members", resetPwd: "/api/members",



  packages: "/api/packages", inventory: "/api/inventory", staff: "/api/staff",



  billingActive: "/api/billing/active", addDrink: "/api/billing/add-drink",



  settle: "/api/billing/settle", billingHistory: "/api/billing/history",



  billingDelete: "/api/billing", billingDraft: "/api/billing", drinkDelete: "/api/billing/drink",



  operationLogs: "/api/operation-logs", adminVerify: "/api/admin/verify",



};







let roomsData=[], membersData=[], packagesData=[], inventoryData=[], staffData=[], activeBillingData=[];
let editingPackageItems=[];
let currentStoredDrinkMember=null, memberStoredDrinksData=[];



let currentRoom=null, currentMember=null, currentBilling=null;



let activeTab="rooms";



let pollingTimers=[], countdownTimers={};

let adminToolsVisible=false;

function applyAdminToolsVisibility(){
  document.querySelectorAll(".del-col,.del-btn,.admin-only").forEach(el=>{el.style.display=adminToolsVisible?"":"none";});
}


async function confirmAdminToolsAccess(){
  const input=document.getElementById("adminToolsPassword");
  const password=input.value;
  if(!password){alert("\u8bf7\u8f93\u5165\u7ba1\u7406\u5bc6\u7801");input.focus();return;}
  try{
    const r=await fetch(API.adminVerify,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({admin_password:password})});
    const j=await r.json();
    if(!r.ok||j.code!==0){alert(j.detail||"\u7ba1\u7406\u5bc6\u7801\u9519\u8bef");input.select();return;}
    adminToolsVisible=true;
    applyAdminToolsVisibility();
    closeModal("adminToolsModal");
    input.value="";
  }catch(e){alert("\u9a8c\u8bc1\u5931\u8d25: "+e);}
}







// ---- Init ----



document.addEventListener("DOMContentLoaded", () => {



  setupTabs();



  updateClock(); setInterval(updateClock, 1000);



  document.getElementById("confirmOpen")?.addEventListener("click", confirmOpen);



  document.getElementById("confirmExtend")?.addEventListener("click", confirmExtend);



  document.getElementById("confirmBooking")?.addEventListener("click", confirmBooking);



  document.getElementById("confirmMember")?.addEventListener("click", confirmMember);



  document.getElementById("confirmEditMember")?.addEventListener("click", confirmEditMember);



  document.getElementById("confirmRecharge")?.addEventListener("click", confirmRecharge);



  document.getElementById("confirmResetPwd")?.addEventListener("click", confirmResetPwd);

  document.getElementById("confirmStoreDrink")?.addEventListener("click", confirmStoreDrink);



  document.getElementById("confirmPackage")?.addEventListener("click", confirmPackage);






  document.getElementById("confirmDeletePkg")?.addEventListener("click", confirmDeletePkg);



  document.getElementById("confirmInventory")?.addEventListener("click", confirmInventory);

  document.getElementById("confirmStaff")?.addEventListener("click", confirmStaff);

  document.getElementById("confirmAdminTools")?.addEventListener("click", confirmAdminToolsAccess);
  document.getElementById("adminToolsPassword")?.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();confirmAdminToolsAccess();}});



  // Close modals via overlay click or X button



  document.querySelectorAll(".modal-overlay").forEach(ov => {



    ov.addEventListener("click", e => { if (e.target===ov) closeModal(ov.id); });



    const m=ov.querySelector(".modal"); if(m&&!m.querySelector(".modal-close")){



      const x=document.createElement("button"); x.className="modal-close"; x.innerHTML="&times;";



      x.addEventListener("click",()=>closeModal(ov.id)); m.appendChild(x);



    }



  });



  document.getElementById("settlePayment")?.addEventListener("change",function(){



    document.getElementById("memberSettleInfo").style.display=this.value==="会员余额"?"block":"none";



  });



  switchTab("rooms");



// ---- Ctrl+/ toggle sensitive management fields ----




document.addEventListener("keydown",function(e){
  if(!e.ctrlKey||e.shiftKey||(e.key!=="/"&&e.code!=="Slash")||e.repeat)return;
  e.preventDefault();
  if(adminToolsVisible){adminToolsVisible=false;applyAdminToolsVisibility();return;}
  const input=document.getElementById("adminToolsPassword");
  input.value="";
  showModal("adminToolsModal");
  setTimeout(()=>input.focus(),0);
});



});







function updateClock(){document.getElementById("clock").textContent=new Date().toLocaleString("zh-CN",{hour12:false});}



function showModal(id){document.getElementById(id).classList.add("show");}



function closeModal(id){document.getElementById(id).classList.remove("show");}







// ---- Tabs ----



function setupTabs(){document.querySelectorAll(".tab-btn").forEach(b=>b.addEventListener("click",()=>switchTab(b.dataset.tab)));}

function clearPolling(){pollingTimers.forEach(clearInterval);pollingTimers=[];}

function addPolling(fn, interval){pollingTimers.push(setInterval(fn, interval));}

function switchTab(tab){
  activeTab=tab;
  document.querySelectorAll(".tab-btn").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
  document.querySelectorAll(".tab-panel").forEach(p=>p.classList.toggle("active",p.id==="tab-"+tab));
  clearPolling();

  if(tab==="rooms"){
    fetchRooms();fetchBookings();fetchPowerStatus();
    addPolling(fetchRooms,5000);addPolling(fetchBookings,30000);addPolling(fetchPowerStatus,15000);
  }else if(tab==="members"){
    fetchMembers();addPolling(fetchMembers,10000);
  }else if(tab==="checkout"){
    fetchActiveBilling();fetchInventory();fetchPackages();addPolling(fetchActiveBilling,10000);
  }else if(tab==="packages"){
    fetchPackages();fetchInventory();
  }else if(tab==="inventory"){
    fetchInventory();
  }else if(tab==="staff"){
    fetchStaff();
  }else if(tab==="history"){
    fetchBillingHistory();
  }else if(tab==="logs"){
    fetchOpLogs();
  }
}


// ================================================================

// Room Management



// ================================================================







async function fetchRooms(){
  const notice=document.getElementById("roomsNotice");
  try{
    const r=await fetch(API.rooms),j=await r.json();
    if(!r.ok||j.code!==0)throw new Error(j.detail||j.msg||"房间接口异常");
    roomsData=j.data||[];
    renderRooms();
    if(j.source==="cache"){
      notice.textContent=j.warning||"设备服务器暂时无法连接，当前显示缓存房间。";
      notice.style.display="block";
      document.getElementById("serverStatus").classList.add("offline");
    }else{
      notice.style.display="none";
      document.getElementById("serverStatus").classList.remove("offline");
    }
  }catch(e){
    document.getElementById("serverStatus").classList.add("offline");
    notice.textContent="房间数据加载失败："+e.message;
    notice.style.display="block";
    if(!roomsData.length)document.getElementById("roomsGrid").innerHTML='<div class="empty-hint room-load-error">暂无可显示房间，请检查设备服务器或房间缓存。</div>';
  }
}







async function fetchPowerStatus(){try{const r=await fetch(API.roomStatus);const j=await r.json();if(j.code===0)renderPowerStrip(j.data);}catch(e){}}







function renderPowerStrip(data){



  const s=document.getElementById("powerStrip"),ps=new Set((data||[]).map(d=>d.ip));



  const items=roomsData.map(r=>{const on=ps.has(r.room_ip);return '<span class="'+(on?"ps-item":"ps-item offline")+'">'+r.room_no+" "+(on?"已通电":"未通电")+'</span>';});



  s.innerHTML=items.length?'<span class="ps-label">房间通电状态</span>'+items.join(""):'<span style="color:var(--text-dim);font-size:13px;">房间通电状态：暂无数据</span>';



}







function renderRooms(){



  const g=document.getElementById("roomsGrid");

  if(!roomsData.length){g.innerHTML='<div class="empty-hint room-load-error">暂无房间数据</div>';return;}



  g.innerHTML=roomsData.map(r=>{



    const sc=r.powered_on?"state-"+r.room_state:"offline";



    const bc=!r.powered_on?"badge-offline":r.room_state===1?"badge-active":"badge-idle";



    const bt=!r.powered_on?"未通电":r.room_state===1?"已开台":"空闲";



    let th="";if(r.room_state===1&&r.auto_close_at)th='<div class="room-timer" id="timer-'+r.room_no+'">--:--:--</div>';else if(r.room_state===1)th='<div class="room-timer">开台中</div>';



    let info=r.powered_on?"IP: "+r.room_ip+" | MAC: "+r.room_mac:"房间未通电";



    let act="";if(!r.powered_on)act='<span style="color:var(--text-dim);font-size:13px;">房间未通电</span>';



    else if(r.room_state===0)act='<button class="btn btn-primary" onclick="openRoom(\''+r.room_no+'\')">开台</button>';



    else act='<button class="btn btn-outline" onclick="extendRoom(\''+r.room_no+'\')">续时</button><button class="btn btn-danger" onclick="closeRoom(\''+r.room_no+'\')">关台</button>';



    return '<div class="room-card '+sc+'"><div class="room-header"><span class="room-no">'+r.room_no+'</span><span class="room-badge '+bc+'">'+bt+'</span></div><div class="room-info">'+info+'</div>'+th+'<div class="room-actions">'+act+'</div></div>';



  }).join("");



  updateAllCountdowns();



}







function updateAllCountdowns(){roomsData.forEach(r=>{if(r.room_state===1&&r.auto_close_at)startCountdown("timer-"+r.room_no,r.auto_close_at);});}







function startCountdown(eid,closeAt){



  if(countdownTimers[eid])clearInterval(countdownTimers[eid]);



  const el=document.getElementById(eid);if(!el)return;



  const tick=()=>{const d=new Date(closeAt)-new Date();if(d<=0){el.textContent="00:00:00";el.classList.add("countdown-warning");if(countdownTimers[eid])clearInterval(countdownTimers[eid]);return;}el.textContent=String(Math.floor(d/3600000)).padStart(2,"0")+":"+String(Math.floor((d%3600000)/60000)).padStart(2,"0")+":"+String(Math.floor((d%60000)/1000)).padStart(2,"0");el.classList.toggle("countdown-warning",d<300000);};



  tick();countdownTimers[eid]=setInterval(tick,1000);



}







// ---- Duration helpers ----



function onOpenDurationChange(){document.getElementById("openCustomDur").style.display=document.getElementById("openDuration").value==="custom"?"flex":"none";}



function onExtendDurationChange(){document.getElementById("extendCustomDur").style.display=document.getElementById("extendDuration").value==="custom"?"flex":"none";}



function onBookingDurationChange(){document.getElementById("bookingCustomDur").style.display=document.getElementById("bookingDuration").value==="custom"?"flex":"none";}



function getDuration(selId,hId,mId){const v=document.getElementById(selId).value;if(v==="unlimited")return{type:"unlimited",min:null};if(v==="custom"){const h=parseInt(document.getElementById(hId).value)||0,m=parseInt(document.getElementById(mId).value)||0,t=h*60+m;if(t<1)return null;return{type:"timed",min:t};}return{type:"timed",min:parseInt(v)};}







// ---- Open Room ----



async function openRoom(roomNo){



  currentRoom=roomsData.find(r=>r.room_no===roomNo);if(!currentRoom)return;



  if(!(await checkRoomBillable(roomNo)))return;



  document.getElementById("openRoomLabel").textContent=roomNo;



  document.getElementById("openDuration").value="180";onOpenDurationChange();



  showModal("openModal");



}







async function confirmOpen(){



  if(!currentRoom)return;



  const dur=getDuration("openDuration","openHours","openMins");if(!dur)return;



  const body={room_ip:currentRoom.room_ip,room_name:currentRoom.room_no,duration_type:dur.type,duration_minutes:dur.min,customer_type:"retail"};



  try{
    const r=await fetch(API.open,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),j=await r.json();
    if(j.code===0){closeModal("openModal");fetchRooms();}
    else if(r.status===409){closeModal("openModal");alert(j.detail||"该房间有待结账账单，请先结账");switchTab("checkout");}
    else alert("开台失败："+(j.detail||j.msg||"unknown"));
  }



  catch(e){alert("请求失败: "+e);}



}







// ---- Close ----



async function closeRoom(roomNo){



  const room=roomsData.find(r=>r.room_no===roomNo);if(!room)return;



  if(!confirm("确认关台 "+roomNo+"？"))return;



  try{
    const r=await fetch(API.close,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({room_ip:room.room_ip,room_name:room.room_no})}),j=await r.json();
    if(j.code===0){alert("关台成功，账单已转到收银台，请完成结账。");switchTab("checkout");}
    else alert("关台失败: "+(j.detail||j.msg||"unknown"));
  }



  catch(e){alert("请求失败: "+e);}



}







// ---- Extend ----



function extendRoom(roomNo){



  currentRoom=roomsData.find(r=>r.room_no===roomNo);if(!currentRoom)return;



  document.getElementById("extendRoomLabel").textContent=roomNo;



  document.getElementById("extendDuration").value="60";onExtendDurationChange();



  showModal("extendModal");



}







async function confirmExtend(){



  if(!currentRoom)return;



  const dur=getDuration("extendDuration","extendHours","extendMins");if(!dur||!dur.min)return;



  try{const r=await fetch(API.extend,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({room_ip:currentRoom.room_ip,room_name:currentRoom.room_no,duration_minutes:dur.min})});const j=await r.json();if(j.code===0){closeModal("extendModal");fetchRooms();}else alert("续时失败: "+(j.detail||j.msg||"unknown"));}



  catch(e){alert("请求失败: "+e);}



}







// ---- Bookings ----



async function fetchBookings(){try{const r=await fetch(API.bookings);const j=await r.json();if(j.code===0)renderBookings(j.data);}catch(e){}}



function renderBookings(bookings){const l=document.getElementById("bookingsList"),p=bookings.filter(b=>b.status==="pending");if(!p.length){l.innerHTML='<p class="empty-hint">暂无预订</p>';return;}l.innerHTML=p.map(b=>{const t=new Date(b.open_at);return '<div class="booking-item"><span class="booking-room">'+b.room_name+'</span><span class="booking-time">'+t.toLocaleString("zh-CN",{hour12:false})+'</span><button class="booking-cancel" onclick="cancelBooking(\''+b.id+'\')" title="取消">x</button></div>';}).join("");}



function showBookingModal(){const s=document.getElementById("bookingRoom");s.innerHTML=roomsData.map(r=>'<option value="'+r.room_no+'" data-ip="'+r.room_ip+'">'+r.room_no+'</option>').join("");const t=new Date(Date.now()+3600000);t.setMinutes(Math.ceil(t.getMinutes()/5)*5,0,0);document.getElementById("bookingTime").value=t.getFullYear()+"-"+String(t.getMonth()+1).padStart(2,"0")+"-"+String(t.getDate()).padStart(2,"0")+"T"+String(t.getHours()).padStart(2,"0")+":"+String(t.getMinutes()).padStart(2,"0");document.getElementById("bookingDuration").value="120";onBookingDurationChange();showModal("bookingModal");}



async function confirmBooking(){const s=document.getElementById("bookingRoom"),roomNo=s.value,roomIp=s.selectedOptions[0].dataset.ip,openAt=document.getElementById("bookingTime").value;const dur=getDuration("bookingDuration","bookingHours","bookingMins");if(!openAt||!dur)return;try{const r=await fetch(API.bookings,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({room_ip:roomIp,room_name:roomNo,open_at:new Date(openAt).toISOString(),duration_type:dur.type,duration_minutes:dur.min,customer_type:"retail"})});const j=await r.json();if(j.code===0){closeModal("bookingModal");fetchBookings();}else alert("预订失败: "+(j.detail||j.msg||"unknown"));}catch(e){alert("请求失败: "+e);}}



async function cancelBooking(id){if(!confirm("确认取消预订？"))return;try{await fetch(API.bookings+"/"+id,{method:"DELETE"});fetchBookings();}catch(e){alert("取消失败: "+e);}}







// ================================================================



// Member Management (unchanged)



// ================================================================







async function fetchMembers(){try{const r=await fetch(API.members);const j=await r.json();if(j.code===0){membersData=j.data;renderMembers();}}catch(e){}}



function renderMembers(){
  const tb=document.querySelector("#membersTable tbody");
  if(!membersData.length){tb.innerHTML='<tr><td colspan="5" class="empty-hint">暂无会员数据</td></tr>';return;}
  tb.innerHTML=membersData.map(m=>{
    const cr=m.created_at?m.created_at.replace("T"," ").substring(0,19):"-";
    return '<tr><td>'+escapeHtml(m.name)+'</td><td>'+escapeHtml(m.phone)+'</td><td>'+Number(m.balance||0).toFixed(2)+'</td><td style="font-size:12px;color:var(--text-dim);">'+cr+'</td><td><button class="btn btn-xs btn-accent" onclick="showRechargeModal('+m.id+')">充值</button> <button class="btn btn-xs btn-outline" onclick="showStoredDrinksModal('+m.id+')">存酒</button> <button class="btn btn-xs btn-outline" onclick="showEditMemberModal('+m.id+')">编辑</button> <button class="btn btn-xs btn-secondary" onclick="showResetPwdModal('+m.id+')">重置密码</button></td></tr>';
  }).join("");
}

function escapeHtml(value){return String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));}

async function showStoredDrinksModal(memberId){
  const member=membersData.find(item=>item.id===memberId);if(!member)return;
  currentStoredDrinkMember=member;
  document.getElementById("storedDrinksMemberLabel").textContent=member.name+"（"+member.phone+"）";
  document.getElementById("storedDrinkName").value="";
  document.getElementById("storedDrinkKind").value="sealed";
  document.getElementById("storedDrinkQty").value="1";
  document.getElementById("storedDrinkLocation").value="";
  document.getElementById("storedDrinkNotes").value="";
  onStoredDrinkKindChange();
  showModal("storedDrinksModal");
  fetchStoredDrinkOptions();
  await fetchMemberStoredDrinks();
}

async function fetchStoredDrinkOptions(){
  try{
    const r=await fetch(API.inventory),j=await r.json();
    if(j.code!==0)return;
    const names=[...new Set(j.data.filter(item=>item.category==="酒水").map(item=>item.name))];
    document.getElementById("storedDrinkOptions").innerHTML=names.map(name=>'<option value="'+escapeHtml(name)+'"></option>').join("");
  }catch(e){}
}

function onStoredDrinkKindChange(){
  const opened=document.getElementById("storedDrinkKind").value==="opened";
  const qty=document.getElementById("storedDrinkQty");
  document.getElementById("storedDrinkLevelGroup").style.display=opened?"block":"none";
  qty.disabled=opened;
  if(opened)qty.value="1";
}

async function fetchMemberStoredDrinks(){
  if(!currentStoredDrinkMember)return;
  try{
    const r=await fetch(API.members+"/"+currentStoredDrinkMember.id+"/stored-drinks"),j=await r.json();
    if(!r.ok||j.code!==0){alert("读取存酒失败: "+(j.detail||"unknown"));return;}
    memberStoredDrinksData=j.data||[];
    renderMemberStoredDrinks(memberStoredDrinksData,j.logs||[]);
  }catch(e){alert("读取存酒失败: "+e);}
}

function renderMemberStoredDrinks(records,logs){
  const tb=document.querySelector("#storedDrinksTable tbody");
  if(!records.length)tb.innerHTML='<tr><td colspan="6" class="empty-hint">暂无存酒</td></tr>';
  else tb.innerHTML=records.map(item=>{
    const opened=item.storage_kind==="opened";
    const amount=opened?("已开封 · 剩余 "+escapeHtml(item.remaining_level||"未记录")):(item.quantity+" 瓶（未开封）");
    const expiry=item.is_expired?'<span class="storage-expiry expired">已过期</span>':'<span class="storage-expiry">剩 '+item.days_remaining+' 天</span>';
    return '<tr class="'+(item.is_expired?'stored-drink-expired':'')+'"><td><strong>'+escapeHtml(item.item_name)+'</strong>'+(item.notes?'<div class="cell-note">'+escapeHtml(item.notes)+'</div>':'')+'</td><td>'+amount+'</td><td>'+escapeHtml(item.storage_location||"-")+'</td><td class="cell-time">'+escapeHtml((item.stored_at||"").substring(0,16))+'</td><td class="cell-time">'+escapeHtml((item.expires_at||"").substring(0,16))+'<br>'+expiry+'</td><td><button class="btn btn-xs btn-outline" onclick="retrieveStoredDrink('+item.id+')">取酒</button></td></tr>';
  }).join("");
  const ltb=document.querySelector("#storedDrinkLogsTable tbody");
  if(!logs.length)ltb.innerHTML='<tr><td colspan="6" class="empty-hint">暂无记录</td></tr>';
  else ltb.innerHTML=logs.map(log=>{
    const action=log.action==="store"?"存酒":"取酒";
    const kind=log.storage_kind==="opened"?("（已开封 "+escapeHtml(log.remaining_level||"")+'）'):"";
    return '<tr><td class="cell-time">'+escapeHtml((log.created_at||"").substring(0,16))+'</td><td>'+action+'</td><td>'+escapeHtml(log.item_name)+kind+'</td><td>'+log.quantity+' 瓶</td><td>'+log.before_quantity+' → '+log.after_quantity+'</td><td>'+escapeHtml(log.detail||"-")+'</td></tr>';
  }).join("");
}

async function confirmStoreDrink(){
  if(!currentStoredDrinkMember)return;
  const kind=document.getElementById("storedDrinkKind").value;
  const data={
    item_name:document.getElementById("storedDrinkName").value.trim(),
    storage_kind:kind,
    quantity:kind==="opened"?1:parseInt(document.getElementById("storedDrinkQty").value,10),
    remaining_level:kind==="opened"?document.getElementById("storedDrinkLevel").value:null,
    storage_location:document.getElementById("storedDrinkLocation").value.trim()||null,
    notes:document.getElementById("storedDrinkNotes").value.trim()||null
  };
  if(!data.item_name){alert("请填写酒水名称");return;}
  if(!Number.isInteger(data.quantity)||data.quantity<1){alert("请输入有效数量");return;}
  if(!confirm("确认给 "+currentStoredDrinkMember.name+" 登记存酒？\n"+data.item_name+"，"+(kind==="opened"?("已开封，剩余 "+data.remaining_level):(data.quantity+" 瓶未开封"))+"\n有效期 30 天"))return;
  try{
    const r=await fetch(API.members+"/"+currentStoredDrinkMember.id+"/stored-drinks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();
    if(!r.ok||j.code!==0){alert("存酒失败: "+(j.detail||"unknown"));return;}
    document.getElementById("storedDrinkName").value="";
    document.getElementById("storedDrinkQty").value="1";
    document.getElementById("storedDrinkNotes").value="";
    await fetchMemberStoredDrinks();
  }catch(e){alert("存酒失败: "+e);}
}

async function retrieveStoredDrink(storageId){
  if(!currentStoredDrinkMember)return;
  const item=memberStoredDrinksData.find(record=>record.id===storageId);if(!item)return;
  let quantity=1;
  if(item.storage_kind==="sealed"){
    const input=prompt("取出多少瓶？当前剩余 "+item.quantity+" 瓶","1");
    if(input===null)return;
    quantity=parseInt(input,10);
    if(!Number.isInteger(quantity)||quantity<1||quantity>item.quantity){alert("请输入 1 到 "+item.quantity+" 之间的整数");return;}
  }
  const expiryWarning=item.is_expired?"\n注意：这批存酒已过期。":"";
  if(!confirm("确认取酒："+item.item_name+"，数量 "+quantity+" 瓶？"+expiryWarning))return;
  try{
    const r=await fetch(API.members+"/"+currentStoredDrinkMember.id+"/stored-drinks/"+storageId+"/retrieve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({quantity})}),j=await r.json();
    if(!r.ok||j.code!==0){alert("取酒失败: "+(j.detail||"unknown"));return;}
    await fetchMemberStoredDrinks();
  }catch(e){alert("取酒失败: "+e);}
}

function showMemberModal(){document.getElementById("memberName").value="";document.getElementById("memberPhone").value="";showModal("memberModal");}



async function confirmMember(){const name=document.getElementById("memberName").value.trim(),phone=document.getElementById("memberPhone").value.trim();if(!name||!phone){alert("请填写姓名和手机号");return;}try{const r=await fetch(API.members,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,phone})});const j=await r.json();if(j.code===0){closeModal("memberModal");fetchMembers();}else alert("添加失败: "+(j.detail||j.msg||"unknown"));}catch(e){alert("请求失败: "+e);}}



function showEditMemberModal(memberId){
  const m=membersData.find(x=>x.id===memberId);if(!m)return;
  currentMember=m;
  document.getElementById("editMemberLabel").textContent=m.name;
  document.getElementById("editMemberName").value=m.name;
  document.getElementById("editMemberPhone").value=m.phone;
  document.getElementById("editMemberBalance").value=Number(m.balance||0).toFixed(2);
  showModal("editMemberModal");
  applyAdminToolsVisibility();
}



async function confirmEditMember(){
  if(!currentMember)return;
  const data={name:document.getElementById("editMemberName").value.trim(),phone:document.getElementById("editMemberPhone").value.trim()};
  if(!data.name||!data.phone){alert("请填写姓名和手机号");return;}
  if(adminToolsVisible){
    const balance=parseFloat(document.getElementById("editMemberBalance").value);
    if(!Number.isFinite(balance)||balance<0){alert("请输入有效余额");return;}
    data.balance=balance;
  }
  try{
    const r=await fetch(API.members+"/"+currentMember.id,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();
    if(j.code===0){closeModal("editMemberModal");fetchMembers();}else alert("修改失败: "+(j.detail||j.msg||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}



function showRechargeModal(memberId){const member=membersData.find(item=>item.id===memberId);if(!member)return;currentMember=member;document.getElementById("rechargeMemberLabel").textContent=member.name;document.getElementById("rechargeAmount").value="";document.getElementById("rechargeMethod").value="现金";showModal("rechargeModal");}



async function confirmRecharge(){if(!currentMember)return;const amount=parseFloat(document.getElementById("rechargeAmount").value),method=document.getElementById("rechargeMethod").value;if(!amount||amount<=0){alert("请输入有效金额");return;}try{const r=await fetch(API.recharge+"/"+currentMember.id+"/recharge",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({amount,payment_method:method})});const j=await r.json();if(j.code===0){closeModal("rechargeModal");fetchMembers();}else alert("充值失败："+(j.detail||j.msg||"unknown"));}catch(e){alert("请求失败: "+e);}}



function showResetPwdModal(memberId){
  const member=membersData.find(item=>item.id===memberId);if(!member)return;
  currentMember=member;
  document.getElementById("resetPwdLabel").textContent=member.name;
  document.getElementById("resetPwdNew").value="";
  showModal("resetPwdModal");
}

async function confirmResetPwd(){
  if(!currentMember)return;
  const newPwd=document.getElementById("resetPwdNew").value.trim();
  if(!newPwd||newPwd.length<4){alert("新密码至少4位");return;}
  try{
    const r=await fetch(API.resetPwd+"/"+currentMember.id+"/reset-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({new_password:newPwd})});
    const j=await r.json();
    if(j.code===0){closeModal("resetPwdModal");alert("密码已重置");}
    else alert("重置失败: "+(j.detail||j.msg||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}
// ================================================================



// Package Management



// ================================================================







async function fetchPackages(){
  try{const r=await fetch(API.packages),j=await r.json();if(j.code===0){packagesData=j.data;renderPackages();}}catch(e){}
}
function onPkgTypeChange(){renderPackages();}
function packageItemSummary(items){
  if(!items||!items.length)return "无附带酒水/小吃";
  return items.map(i=>(i.item_type==="drink"?"酒水：":"小吃：")+i.item_name+"×"+i.qty+(i.unit_label||(i.item_type==="snack"?"份":""))).join("，");
}
function renderPackages(){
  const filter=document.getElementById("pkgTypeFilter").value,filtered=packagesData.filter(p=>p.type===filter),tb=document.querySelector("#packagesTable tbody");
  document.getElementById("pkgTypeLabel").textContent=filter==="open"?"开台套餐":"续时套餐";
  if(!filtered.length){tb.innerHTML='<tr><td colspan="5" class="empty-hint">暂无套餐</td></tr>';return;}
  tb.innerHTML=filtered.map(p=>'<tr><td>'+p.name+'</td><td>'+p.duration_minutes+'</td><td>'+Number(p.price_normal||0).toFixed(2)+'</td><td style="font-size:12px;color:var(--text-dim);">'+packageItemSummary(p.items)+'</td><td><button class="btn btn-xs btn-outline" onclick="showEditPackageModal('+p.id+')">编辑</button> <button class="btn btn-xs btn-danger" onclick="showDeletePkgModal('+p.id+',\''+p.name+'\')">删除</button></td></tr>').join("");
}
function populatePackageDrinkOptions(){
  const drinks=inventoryData.filter(i=>["酒水","饮料"].includes(i.category));
  document.getElementById("pkgDrinkInventory").innerHTML=drinks.length?drinks.map(i=>'<option value="'+i.id+'">'+escapeHtml(i.category+' - '+i.name)+'（库存 '+inventoryStockText(i)+'）</option>').join(""):'<option value="">请先在库存管理新增酒水或饮料</option>';
}
function renderPackageItemEditor(){
  const indexed=editingPackageItems.map((item,index)=>({item,index})),drinks=indexed.filter(x=>x.item.item_type==="drink"),snacks=indexed.filter(x=>x.item.item_type==="snack");
  document.getElementById("pkgDrinkList").innerHTML=drinks.length?drinks.map(x=>'<div style="display:flex;justify-content:space-between;padding:4px 0;"><span>'+x.item.item_name+' × '+x.item.qty+(x.item.unit_label||"瓶")+'</span><button type="button" class="btn btn-xs btn-danger" onclick="removePackageItem('+x.index+')">移除</button></div>').join(""):"暂未添加酒水";
  document.getElementById("pkgSnackList").innerHTML=snacks.length?snacks.map(x=>'<div style="display:flex;justify-content:space-between;padding:4px 0;"><span>'+x.item.item_name+' × '+x.item.qty+'份</span><button type="button" class="btn btn-xs btn-danger" onclick="removePackageItem('+x.index+')">移除</button></div>').join(""):"暂未添加小吃";
}
function showPackageModal(){
  editingPackageItems=[];document.getElementById("packageModalTitle").textContent="新增套餐";document.getElementById("editPackageId").value="";document.getElementById("pkgName").value="";document.getElementById("pkgType").value=document.getElementById("pkgTypeFilter").value;document.getElementById("pkgDuration").value="180";document.getElementById("pkgPriceNormal").value="0";document.getElementById("pkgDrinkQty").value="1";document.getElementById("pkgSnackName").value="";document.getElementById("pkgSnackQty").value="1";populatePackageDrinkOptions();renderPackageItemEditor();showModal("packageModal");
}
function showEditPackageModal(pkgId){
  const p=packagesData.find(x=>x.id===pkgId);if(!p)return;editingPackageItems=(p.items||[]).map(item=>({...item}));document.getElementById("packageModalTitle").textContent="编辑套餐";document.getElementById("editPackageId").value=p.id;document.getElementById("pkgName").value=p.name||"";document.getElementById("pkgType").value=p.type;document.getElementById("pkgDuration").value=p.duration_minutes;document.getElementById("pkgPriceNormal").value=p.price_normal||0;document.getElementById("pkgDrinkQty").value="1";document.getElementById("pkgSnackName").value="";document.getElementById("pkgSnackQty").value="1";populatePackageDrinkOptions();renderPackageItemEditor();showModal("packageModal");
}
function addPackageDrinkItem(){
  const inventoryId=parseInt(document.getElementById("pkgDrinkInventory").value),qty=parseInt(document.getElementById("pkgDrinkQty").value)||1,inventory=inventoryData.find(i=>i.id===inventoryId);if(!inventory){alert("请先选择酒水商品");return;}const existing=editingPackageItems.find(i=>i.item_type==="drink"&&i.inventory_id===inventoryId);if(existing)existing.qty+=qty;else editingPackageItems.push({item_type:"drink",inventory_id:inventoryId,item_name:inventory.name,qty,unit_label:inventory.unit_name||"瓶"});renderPackageItemEditor();
}
function addPackageSnackItem(){
  const name=document.getElementById("pkgSnackName").value.trim(),qty=parseInt(document.getElementById("pkgSnackQty").value)||1;if(!name){alert("请填写小吃名称");return;}const existing=editingPackageItems.find(i=>i.item_type==="snack"&&i.item_name===name);if(existing)existing.qty+=qty;else editingPackageItems.push({item_type:"snack",item_name:name,qty,unit_label:"份"});document.getElementById("pkgSnackName").value="";renderPackageItemEditor();
}
function removePackageItem(index){editingPackageItems.splice(index,1);renderPackageItemEditor();}
async function confirmPackage(){
  const editId=document.getElementById("editPackageId").value,data={name:document.getElementById("pkgName").value.trim(),type:document.getElementById("pkgType").value,duration_minutes:parseInt(document.getElementById("pkgDuration").value)||0,price_normal:parseFloat(document.getElementById("pkgPriceNormal").value)||0,items:editingPackageItems.map(i=>i.item_type==="drink"?{item_type:"drink",inventory_id:i.inventory_id,qty:i.qty}:{item_type:"snack",item_name:i.item_name,qty:i.qty})};
  if(!data.name||data.duration_minutes<1){alert("请填写套餐名称和有效时长");return;}
  try{const r=editId?await fetch(API.packages+"/"+editId,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}):await fetch(API.packages,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();if(r.ok&&j.code===0){closeModal("packageModal");fetchPackages();}else alert((editId?"修改":"新增")+"失败: "+(j.detail||j.msg||"unknown"));}catch(e){alert("请求失败: "+e);}
}
function showDeletePkgModal(pkgId,pkgName){document.getElementById("deletePkgName").textContent=pkgName;document.getElementById("deletePkgPassword").value="";document.getElementById("confirmDeletePkg").onclick=async()=>{const pwd=document.getElementById("deletePkgPassword").value;try{const r=await fetch(API.packages+"/"+pkgId,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({admin_password:pwd})});const j=await r.json();if(j.code===0){closeModal("deletePkgModal");fetchPackages();}else alert("删除失败: "+(j.detail||"unknown"));}catch(e){alert("请求失败: "+e);}};showModal("deletePkgModal");}



async function confirmDeletePkg(){}







// ================================================================



// Inventory



// ================================================================







async function fetchInventory(){
  try{
    const r=await fetch(API.inventory),j=await r.json();
    if(j.code===0){inventoryData=j.data;renderInventory();}
  }catch(e){}
}

const INVENTORY_UNITS={"酒水":"瓶","饮料":"瓶","零食":"份","水果":"份"};
function inventoryUnitFor(category){return INVENTORY_UNITS[category]||"份";}
function inventoryTracksStock(item){return item&&["酒水","饮料"].includes(item.category);}

function onInventoryCategoryChange(){
  const category=document.getElementById("invCategory").value;
  const unit=inventoryUnitFor(category);
  document.getElementById("invUnitName").value=unit;
  document.getElementById("invUnitHint").textContent=unit+"（按分类自动设置）";
  document.getElementById("invStockLabel").textContent="库存总数（"+unit+"）";
  const tracks=category==="酒水"||category==="饮料";
  document.getElementById("invStockHint").textContent=tracks?(category+"销售后自动扣库存"):(category+"只记账，不自动扣库存，数量手动维护");
  const caseFields=document.getElementById("inventoryCaseFields");
  caseFields.style.display=category==="酒水"?"grid":"none";
  if(category!=="酒水"){
    document.getElementById("invCaseSize").value="0";
    document.getElementById("invCasePrice").value="0";
  }
}

function inventoryStockText(item){
  const stock=Number(item.stock||0);
  const unit=item.unit_name||inventoryUnitFor(item.category);
  const caseSize=Number(item.case_size||0);
  if(item.category==="酒水"&&caseSize>=2){
    const cases=Math.floor(stock/caseSize),remainder=stock%caseSize;
    return cases+"箱 "+remainder+unit+"（总"+stock+unit+"）";
  }
  return stock+unit;
}

function renderInventory(){
  const tb=document.querySelector("#inventoryTable tbody");
  if(!inventoryData.length){tb.innerHTML='<tr><td colspan="9" class="empty-hint">暂无库存</td></tr>';return;}
  tb.innerHTML=inventoryData.map(i=>{
    const unit=i.unit_name||inventoryUnitFor(i.category);
    const caseSize=Number(i.case_size||0);
    const hasCase=i.category==="酒水"&&caseSize>=2;
    const caseSpec=hasCase?caseSize+unit+"/箱":"-";
    const casePrice=hasCase?Number(i.case_price||0).toFixed(2):"-";
    const low=inventoryTracksStock(i)&&Number(i.stock||0)<=Number(i.low_stock??5);
    const linkage=inventoryTracksStock(i)?"":"<div class=\"cell-note\">手动维护</div>";
    return '<tr><td>'+escapeHtml(i.category)+'</td><td>'+escapeHtml(i.name)+'</td><td>'+unit+'</td><td>'+Number(i.unit_price||0).toFixed(2)+'</td><td>'+caseSpec+'</td><td>'+casePrice+'</td><td class="admin-only" style="display:none;">'+Number(i.cost_price||0).toFixed(2)+'</td><td style="'+(low?'color:var(--danger);font-weight:700;':'')+'">'+inventoryStockText(i)+linkage+'</td><td><button class="btn btn-xs btn-outline" onclick="showEditInventoryModal('+i.id+')">编辑</button> <button class="btn btn-xs btn-danger del-btn" style="display:none;" onclick="deleteInventory('+i.id+')">删除</button></td></tr>';
  }).join("");
  applyAdminToolsVisibility();
}

function showInventoryModal(){
  document.getElementById("inventoryModalTitle").textContent="新增库存物品";
  document.getElementById("editInvId").value="";
  document.getElementById("invCategory").value="酒水";
  document.getElementById("invName").value="";
  document.getElementById("invPrice").value="0";
  document.getElementById("invCaseSize").value="0";
  document.getElementById("invCasePrice").value="0";
  document.getElementById("invCostPrice").value="0";
  document.getElementById("invStock").value="0";
  document.getElementById("invLowStock").value="5";
  onInventoryCategoryChange();
  showModal("inventoryModal");
  applyAdminToolsVisibility();
}

function showEditInventoryModal(itemId){
  const i=inventoryData.find(x=>x.id===itemId);if(!i)return;
  document.getElementById("inventoryModalTitle").textContent="编辑库存物品";
  document.getElementById("editInvId").value=itemId;
  document.getElementById("invCategory").value=i.category;
  document.getElementById("invName").value=i.name;
  document.getElementById("invPrice").value=Number(i.unit_price||0);
  document.getElementById("invStock").value=Number(i.stock||0);
  document.getElementById("invLowStock").value=Number(i.low_stock??5);
  document.getElementById("invCostPrice").value=Number(i.cost_price||0);
  onInventoryCategoryChange();
  if(i.category==="酒水"){
    document.getElementById("invCaseSize").value=Number(i.case_size||0);
    document.getElementById("invCasePrice").value=Number(i.case_price||0);
  }
  showModal("inventoryModal");
  applyAdminToolsVisibility();
}

async function confirmInventory(){
  const editId=document.getElementById("editInvId").value;
  const category=document.getElementById("invCategory").value;
  const isAlcohol=category==="酒水";
  const data={
    category,
    name:document.getElementById("invName").value.trim(),
    unit_name:inventoryUnitFor(category),
    unit_price:parseFloat(document.getElementById("invPrice").value)||0,
    case_size:isAlcohol?(parseInt(document.getElementById("invCaseSize").value)||0):0,
    case_price:isAlcohol?(parseFloat(document.getElementById("invCasePrice").value)||0):0,
    stock:parseInt(document.getElementById("invStock").value)||0,
    low_stock:parseInt(document.getElementById("invLowStock").value)||0
  };
  if(data.case_size<2){data.case_size=0;data.case_price=0;}
  if(adminToolsVisible)data.cost_price=parseFloat(document.getElementById("invCostPrice").value)||0;
  if(!data.name){alert("请填写物品名称");return;}
  if(editId){
    const original=inventoryData.find(x=>x.id===parseInt(editId));
    if(original&&data.stock!==Number(original.stock||0)){
      const password=prompt("手动修改库存量，请输入管理密码");
      if(!password)return;
      data.admin_password=password;
    }
  }
  try{
    const r=await fetch(editId?API.inventory+"/"+editId:API.inventory,{method:editId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    const j=await r.json();
    if(r.ok&&j.code===0){closeModal("inventoryModal");fetchInventory();}
    else alert("操作失败: "+(j.detail||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}
async function deleteInventory(itemId){
  if(!confirm("确认删除该库存物品？"))return;
  try{
    const r=await fetch(API.inventory+"/"+itemId,{method:"DELETE"}),j=await r.json();
    if(j.code===0)fetchInventory();else alert("删除失败: "+(j.detail||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}

// Staff

// ================================================================

async function fetchStaff(){
  try{
    const r=await fetch(API.staff),j=await r.json();
    if(j.code===0){staffData=j.data;renderStaff();}
  }catch(e){}
}

function renderStaff(){
  const tb=document.querySelector("#staffTable tbody");
  if(!staffData.length){tb.innerHTML='<tr><td colspan="7" class="empty-hint">&#26242;&#26080;&#24215;&#20869;&#20154;&#21592;</td></tr>';return;}
  tb.innerHTML=staffData.map(s=>'<tr><td>'+s.name+'</td><td>'+(s.phone||'-')+'</td><td>'+s.position+'</td><td><span class="status-badge '+(s.status==="\u5728\u804c"?'active':'inactive')+'">'+s.status+'</span></td><td class="admin-only" style="display:none;">'+Number(s.salary||0).toFixed(2)+'</td><td>'+(s.notes||'-')+'</td><td><button class="btn btn-xs btn-outline" onclick="showEditStaffModal('+s.id+')">&#32534;&#36753;</button> <button class="btn btn-xs btn-danger del-btn" style="display:none;" onclick="deleteStaff('+s.id+')">&#21024;&#38500;</button></td></tr>').join("");
  applyAdminToolsVisibility();
}


function showStaffModal(){
  document.getElementById("staffModalTitle").textContent="\u65b0\u589e\u5e97\u5185\u4eba\u5458";
  document.getElementById("editStaffId").value="";
  document.getElementById("staffName").value="";
  document.getElementById("staffPhone").value="";
  document.getElementById("staffPosition").value="\u5458\u5de5";
  document.getElementById("staffStatus").value="\u5728\u804c";
  document.getElementById("staffSalary").value="0";
  document.getElementById("staffNotes").value="";
  showModal("staffModal");
  applyAdminToolsVisibility();
}


function showEditStaffModal(staffId){
  const s=staffData.find(x=>x.id===staffId);if(!s)return;
  document.getElementById("staffModalTitle").textContent="\u7f16\u8f91\u5e97\u5185\u4eba\u5458";
  document.getElementById("editStaffId").value=staffId;
  document.getElementById("staffName").value=s.name;
  document.getElementById("staffPhone").value=s.phone||"";
  document.getElementById("staffPosition").value=s.position;
  document.getElementById("staffStatus").value=s.status;
  document.getElementById("staffSalary").value=Number(s.salary||0);
  document.getElementById("staffNotes").value=s.notes||"";
  showModal("staffModal");
  applyAdminToolsVisibility();
}


async function confirmStaff(){
  const staffId=document.getElementById("editStaffId").value;
  const data={name:document.getElementById("staffName").value.trim(),phone:document.getElementById("staffPhone").value.trim()||null,position:document.getElementById("staffPosition").value.trim(),status:document.getElementById("staffStatus").value,notes:document.getElementById("staffNotes").value.trim()||null};
  if(adminToolsVisible)data.salary=parseFloat(document.getElementById("staffSalary").value)||0;
  if(!data.name||!data.position){alert("\u8bf7\u586b\u5199\u59d3\u540d\u548c\u5c97\u4f4d");return;}
  try{
    const r=await fetch(staffId?API.staff+"/"+staffId:API.staff,{method:staffId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    const j=await r.json();
    if(j.code===0){closeModal("staffModal");fetchStaff();}else alert("\u64cd\u4f5c\u5931\u8d25: "+(j.detail||"unknown"));
  }catch(e){alert("\u8bf7\u6c42\u5931\u8d25: "+e);}
}

async function deleteStaff(staffId){
  if(!confirm("确认删除这名店内人员？"))return;
  try{const r=await fetch(API.staff+"/"+staffId,{method:"DELETE"}),j=await r.json();if(j.code===0)fetchStaff();else alert("删除失败: "+(j.detail||"unknown"));}catch(e){alert("请求失败: "+e);}
}


// ================================================================



// Billing / Settlement



// ================================================================







function drinkUnitLabel(drink){return drink.unit_label||(drink.sale_unit==="case"?"箱":"瓶");}
function drinkSummaryLine(drink){const label=drinkUnitLabel(drink),price=Number(drink.unit_price||0),subtotal=Number(drink.qty||0)*price,prefix=drink.source==="package"?"[套餐] ":"";return prefix+drink.item_name+" × "+drink.qty+label+" @"+price.toFixed(2)+" = "+subtotal.toFixed(2);}
function renderSettleDrinkSummary(drinks){document.getElementById("settleDrinksSummary").innerHTML=drinks.length?drinks.map(drinkSummaryLine).join("<br>"):"暂无";}
async function fetchActiveBilling(){try{const r=await fetch(API.billingActive);const j=await r.json();if(j.code===0){activeBillingData=j.data;renderActiveBilling(activeBillingData);}}catch(e){}}

function renderActiveBilling(bills){
  const tb=document.querySelector("#billingTable tbody");
  if(!bills.length){tb.innerHTML='<tr><td colspan="5" class="empty-hint">\u6682\u65e0\u5f00\u53f0\u8d26\u5355</td></tr>';return;}
  tb.innerHTML=bills.map(b=>{
    const ct=b.customer_type==="retail"?"\u6563\u6237":("\u4f1a\u5458(id="+b.member_id+")");
    return '<tr><td>'+b.room_no+'</td><td>'+(b.duration_minutes||0)+'</td><td>'+Number(b.drinks_fee||0).toFixed(2)+'</td><td>'+ct+'</td><td><button class="btn btn-xs btn-accent" onclick="showSettle('+b.id+')">\u7ed3\u8d26</button></td></tr>';
  }).join("");
}


function showSettle(billingId){



  fetch(API.billingActive).then(r=>r.json()).then(json=>{



    if(json.code!==0)return;const bill=json.data.find(b=>b.id===billingId);if(!bill)return;



    currentBilling=bill;



    document.getElementById("settleRoomLabel").textContent=bill.room_no;



    const pkgSel=document.getElementById("settlePackage");



    const pkgs=packagesData.filter(p=>p.type==="open");



    pkgSel.innerHTML='<option value="">-- 请选择套餐 --</option>'+pkgs.map(p=>'<option value="'+p.id+'">'+p.name+' ('+p.duration_minutes+'min)</option>').join("");

    pkgSel.value=bill.package_id||"";



    document.getElementById("settleDrinksFee").textContent=(bill.drinks_fee||0).toFixed(2);



    const drinks=bill.drinks||[];



    renderSettleDrinkSummary(drinks);



    document.getElementById("settlePayment").value=bill.payment_method||(bill.customer_type!=="retail"?"\u4f1a\u5458\u4f59\u989d":"\u73b0\u91d1");



    document.getElementById("memberSettleInfo").style.display=bill.customer_type!=="retail"||document.getElementById("settlePayment").value==="会员余额"?"block":"none";



    document.getElementById("settleMemberPhone").value="";
    document.getElementById("settleMemberPassword").value="";
    document.getElementById("settleMemberLabel").textContent="";



    document.getElementById("settleDiscount").value=Number(bill.discount||0).toFixed(2);



    document.getElementById("settleCard").style.display="block";



    updateSettleTotal();



  });



}







function hideSettle(){document.getElementById("settleCard").style.display="none";currentBilling=null;}





function _getPkgPrice(pkg){
  return parseFloat(pkg.price_normal||0);
}

function renderSelectedPackageItems(pkg){document.getElementById("settlePackageItems").textContent="套餐内容："+(pkg?packageItemSummary(pkg.items):"暂无");}
function updateSettleTotal(){
  const pkgId=parseInt(document.getElementById("settlePackage").value),pkg=packagesData.find(p=>p.id===pkgId);renderSelectedPackageItems(pkg);
  if(!pkg){document.getElementById("settleRoomFee").textContent="0";document.getElementById("settleTotal").textContent="0";document.getElementById("maxDiscount").textContent="0";return;}
  const roomFee=_getPkgPrice(pkg);document.getElementById("settleRoomFee").textContent=roomFee.toFixed(2);const drinksFee=parseFloat(document.getElementById("settleDrinksFee").textContent)||0,subtotal=roomFee+drinksFee,discount=parseFloat(document.getElementById("settleDiscount").value)||0,maxDisc=Math.round(subtotal*0.2*100)/100;document.getElementById("maxDiscount").textContent=maxDisc.toFixed(2);if(discount>maxDisc)document.getElementById("settleDiscount").value=maxDisc.toFixed(2);document.getElementById("settleTotal").textContent=Math.max(0,subtotal-Math.min(discount,maxDisc)).toFixed(2);
}
function onSettlePaymentChange(){

  const v=document.getElementById("settlePayment").value;

  document.getElementById("memberSettleInfo").style.display=v==="会员余额"?"block":"none";

}

function lookupSettleMember(){

  const phone=document.getElementById("settleMemberPhone").value.trim();

  if(!phone){alert("请输入会员手机号");return;}

  fetch("/api/members/verify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone,password:""})})

    .then(r=>r.json()).then(j=>{

      if(j.code===0){document.getElementById("settleMemberLabel").textContent="会员: "+j.data.name+"，余额: "+j.data.balance;}

      else{alert(j.detail||"查找失败");}

    }).catch(e=>alert("查找失败: "+e));

}















async function saveSettlementDraft(){
  if(!currentBilling)return;const packageId=parseInt(document.getElementById("settlePackage").value);if(!packageId){alert("请选择套餐");return;}const data={package_id:packageId,payment_method:document.getElementById("settlePayment").value,discount:parseFloat(document.getElementById("settleDiscount").value)||0};
  try{const r=await fetch(API.billingDraft+"/"+currentBilling.id+"/draft",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();if(!r.ok||j.code!==0){alert("保存失败: "+(j.detail||"unknown"));return;}Object.assign(currentBilling,j);currentBilling.drinks=j.drinks||[];document.getElementById("settleDrinksFee").textContent=Number(j.drinks_fee||0).toFixed(2);renderSettleDrinkSummary(currentBilling.drinks);updateSettleTotal();fetchActiveBilling();fetchInventory();alert("当前账单版本已保存，套餐酒水库存已同步，尚未结账");}catch(e){alert("请求失败: "+e);}
}
async function confirmSettle(){



  if(!currentBilling)return;



  const pkgId=parseInt(document.getElementById("settlePackage").value);



  if(!pkgId){alert("请选择套餐");return;}



  const payment=document.getElementById("settlePayment").value;



  const discount=parseFloat(document.getElementById("settleDiscount").value)||0;



  let mp="";



  if(payment==="会员余额")mp=document.getElementById("settleMemberPassword").value;



  try{const r=await fetch(API.settle,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({billing_id:currentBilling.id,package_id:pkgId,payment_method:payment,discount,member_phone:document.getElementById("settleMemberPhone").value,member_password:mp})});const j=await r.json();if(j.code===0){const msg="结账成功！总计："+j.total.toFixed(2);alert(msg);hideSettle();fetchActiveBilling();fetchRooms();if(activeTab==="members")fetchMembers();fetchBillingHistory();}else alert("结账失败: "+(j.detail||"unknown"));}



  catch(e){alert("请求失败: "+e);}



}







// ================================================================



// Operation Logs



// ================================================================







async function fetchOpLogs(){try{const r=await fetch(API.operationLogs+"?limit=100");const j=await r.json();if(j.code===0)renderOpLogs(j.data);}catch(e){}}



function renderOpLogs(logs){const tb=document.querySelector("#logsTable tbody");if(!logs.length){tb.innerHTML='<tr><td colspan="4" class="empty-hint">暂无日志</td></tr>';return;}const labels={open_room:"开台",close_room:"关台",extend_room:"",auto_close:"定时关台",create_booking:"预",cancel_booking:"取消预订",booking_open:"预订开台",booking_failed:"预订失败",create_member:"新增会员",update_member:"编辑会员",recharge_member:"会员充值",reset_member_password:"重置密码",create_package:"新增套餐",update_package:"改",delete_package:"删除套餐",create_staff:"新增店内人员",update_staff:"编辑店内人员",delete_staff:"删除店内人员",create_inventory:"新库",update_inventory:"改库",delete_inventory:"删除库存",add_drink:"添加酒水",update_billing:"编辑账单",save_billing_draft:"保存账单",settle_billing:"结账",store_member_drink:"会员存酒",retrieve_member_drink:"会员取酒"};tb.innerHTML=logs.map(l=>{const t=l.created_at?l.created_at.replace("T"," ").substring(0,19):"-";return '<tr><td style="font-size:12px;color:var(--text-dim);white-space:nowrap;">'+t+'</td><td>'+(labels[l.action]||l.action)+'</td><td>'+(l.room_no||"-")+'</td><td style="font-size:13px;color:var(--text-dim);">'+(l.detail||"-")+'</td></tr>';}).join("");}







// ================================================================



// Billing History



// ================================================================







async function fetchBillingHistory(){try{const r=await fetch(API.billingHistory);const j=await r.json();if(j.code===0)renderBillingHistory(j.data);}catch(e){}}







function renderBillingHistory(bills){



  const tb=document.querySelector("#historyTable tbody");



  if(!bills.length){tb.innerHTML='<tr><td colspan="8" class="empty-hint">暂无记录</td></tr>';return;}



  tb.innerHTML=bills.map(b=>{



    const t=b.close_at?b.close_at.replace("T"," ").substring(0,19):"-";



    const drinks=(b.drinks||[]).map(d=>d.item_name+" x"+d.qty+" @"+(d.unit_price||0)).join(", ")||"-";
    const member=b.settlement_member_name?(b.settlement_member_name+"（"+(b.settlement_member_phone||"无手机号")+"），余额 "+Number(b.member_balance_after||0).toFixed(2)):"-";



    return '<tr><td>'+b.room_no+'</td><td>'+(b.room_fee||0).toFixed(2)+'</td><td>'+(b.drinks_fee||0).toFixed(2)+' <span style="font-size:11px;color:var(--text-dim);">('+drinks+')</span></td><td>'+(b.total||0).toFixed(2)+'</td><td>'+b.payment_method+'</td><td style="font-size:12px;">'+member+'</td><td style="font-size:12px;color:var(--text-dim);">'+t+'</td><td class="del-col" style="display:none;"><button class="btn btn-xs btn-danger del-btn" style="display:none;" onclick="deleteBilling('+b.id+')">删除</button></td></tr>';



  }).join("");
  applyAdminToolsVisibility();



}







async function deleteBilling(billingId){



  if(!confirm("确认删除该结账记录？"))return;



  const pwd=prompt("请输入管理密码");



  if(!pwd)return;



  try{const r=await fetch(API.billingDelete+"/"+billingId+"?admin_password="+encodeURIComponent(pwd),{method:"DELETE"});const j=await r.json();if(j.code===0)fetchBillingHistory();else alert("删除失败: "+(j.detail||"unknown"));}



  catch(e){alert("请求失败: "+e);}



}







// ---- Room lock: check unpaid bills before opening ----



async function checkRoomBillable(roomNo){
  try{
    const r=await fetch(API.billingActive),j=await r.json();
    if(!r.ok||j.code!==0)throw new Error(j.detail||"当前账单接口异常");
    const bill=j.data.find(x=>x.room_no===roomNo);
    if(bill){alert("房间 "+roomNo+" 有待结账账单，请先在收银台结清后再开台。");switchTab("checkout");return false;}
    return true;
  }catch(e){
    alert("无法检查房间账单："+e.message+"。为避免重复开台，本次操作已取消。");
    return false;
  }
}







// ================================================================



// Drinks Modal



// ================================================================







async function showDrinksModal(){
  if(!currentBilling)return;
  document.getElementById("drinksRoomLabel").textContent=currentBilling.room_no;
  try{
    const [billingResponse,inventoryResponse]=await Promise.all([fetch(API.billingActive),fetch(API.inventory)]);
    const billingJson=await billingResponse.json(),inventoryJson=await inventoryResponse.json();
    if(billingJson.code!==0||inventoryJson.code!==0)return;
    const bill=billingJson.data.find(b=>b.id===currentBilling.id);
    if(!bill)return;
    currentBilling=bill;
    inventoryData=inventoryJson.data;
    renderDrinksEditTable(bill.drinks||[]);
    const available=inventoryData.filter(i=>!inventoryTracksStock(i)||Number(i.stock||0)>0);
    const itemSelect=document.getElementById("newDrinkItem");
    itemSelect.innerHTML=available.map(i=>'<option value="'+i.id+'">'+i.category+' - '+i.name+'（'+inventoryStockText(i)+'）</option>').join("");
    document.getElementById("newDrinkQty").value="1";
    onNewDrinkItemChange();
    showModal("drinksModal");
  }catch(e){alert("加载消费明细失败: "+e);}
}

function onNewDrinkItemChange(){
  const itemId=parseInt(document.getElementById("newDrinkItem").value),item=inventoryData.find(i=>i.id===itemId);
  const unitSelect=document.getElementById("newDrinkSaleUnit");
  if(!item){unitSelect.innerHTML="";document.getElementById("newDrinkHint").textContent="暂无可售库存";return;}
  const unit=item.unit_name||inventoryUnitFor(item.category);
  let options='<option value="unit">'+unit+'（'+Number(item.unit_price||0).toFixed(2)+'元）</option>';
  if(item.category==="酒水"&&Number(item.case_size||0)>=2&&Number(item.case_price||0)>0){
    options+='<option value="case">箱（'+item.case_size+unit+'，'+Number(item.case_price||0).toFixed(2)+'元）</option>';
  }
  unitSelect.innerHTML=options;
  updateNewDrinkHint();
}
function updateNewDrinkHint(){
  const itemId=parseInt(document.getElementById("newDrinkItem").value),item=inventoryData.find(i=>i.id===itemId);
  if(!item)return;
  const saleUnit=document.getElementById("newDrinkSaleUnit").value,qty=Math.max(1,parseInt(document.getElementById("newDrinkQty").value)||1);
  const unitSize=saleUnit==="case"?Number(item.case_size||0):1;
  const price=saleUnit==="case"?Number(item.case_price||0):Number(item.unit_price||0);
  const required=qty*unitSize,unit=item.unit_name||inventoryUnitFor(item.category),tracks=inventoryTracksStock(item);
  const enough=!tracks||Number(item.stock||0)>=required;
  const hint=document.getElementById("newDrinkHint");
  hint.textContent=tracks?("库存："+inventoryStockText(item)+"；本次扣减 "+required+unit+"；金额 "+(qty*price).toFixed(2)+" 元"):("本次只记金额，不自动扣库存；金额 "+(qty*price).toFixed(2)+" 元");
  hint.style.color=enough?"var(--text-dim)":"var(--danger)";
}
function renderDrinksEditTable(drinks){
  const tb=document.querySelector("#drinksEditTable tbody");if(!drinks.length){tb.innerHTML='<tr><td colspan="7" style="color:var(--text-dim);padding:20px;">暂无明细</td></tr>';return;}
  tb.innerHTML=drinks.map(d=>{
    const label=drinkUnitLabel(d),subtotal=(Number(d.qty||0)*Number(d.unit_price||0)).toFixed(2),isPackage=d.source==="package";
    const operation=isPackage?'<span style="font-size:12px;color:var(--accent);">套餐包含</span>':'<button class="btn btn-xs btn-danger" onclick="deleteDrink('+d.id+')">删除</button>';
    const stockText=Number(d.stock_qty||0)>0?Number(d.stock_qty):"不联动";
    return '<tr><td>'+(isPackage?'[套餐] ':'')+escapeHtml(d.item_name)+'</td><td>'+label+(Number(d.unit_size||1)>1?'（'+d.unit_size+'基础单位）':'')+'</td><td>'+Number(d.unit_price||0).toFixed(2)+'</td><td>'+d.qty+'</td><td>'+subtotal+'</td><td>'+stockText+'</td><td>'+operation+'</td></tr>';
  }).join("");
}async function addDrinkFromModal(){
  if(!currentBilling)return;
  const inventoryId=parseInt(document.getElementById("newDrinkItem").value),qty=parseInt(document.getElementById("newDrinkQty").value)||1;
  if(!inventoryId){alert("暂无可售库存物品");return;}
  const body={billing_id:currentBilling.id,inventory_id:inventoryId,sale_unit:document.getElementById("newDrinkSaleUnit").value,qty};
  try{
    const r=await fetch(API.addDrink,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),j=await r.json();
    if(r.ok&&j.code===0)showDrinksModal();else alert("添加失败: "+(j.detail||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}

async function deleteDrink(drinkId){
  if(!confirm("确认删除该明细？已扣库存的商品会自动退回库存。"))return;
  const r=await fetch(API.drinkDelete+"/"+drinkId,{method:"DELETE"}),j=await r.json();
  if(r.ok&&j.code===0)showDrinksModal();else alert("删除失败: "+(j.detail||"unknown"));
}
function closeDrinksModal(){
  closeModal("drinksModal");
  if(currentBilling){
    fetch(API.billingActive).then(r=>r.json()).then(json=>{
      if(json.code!==0)return;
      const bill=json.data.find(b=>b.id===currentBilling.id);if(!bill)return;
      currentBilling=bill;
      document.getElementById("settleDrinksFee").textContent=Number(bill.drinks_fee||0).toFixed(2);
      renderSettleDrinkSummary(bill.drinks||[]);
      updateSettleTotal();
      fetchInventory();
    });
  }
}

function saveDrinksModal(){closeDrinksModal();}




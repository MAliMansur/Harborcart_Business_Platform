"use strict";
const money = value => new Intl.NumberFormat("en-US", {style:"currency", currency:"USD"}).format(value / 100);
const notice = (message, error=false) => {
  const box = document.getElementById("notice");
  if (!box) return;
  box.textContent = message;
  box.className = "notice " + (error ? "error" : "success");
  box.hidden = false;
  box.scrollIntoView({block:"nearest", behavior:"smooth"});
};
function csrf() {
  const entry = document.cookie.split("; ").find(row => row.startsWith("csrftoken="));
  return entry ? decodeURIComponent(entry.slice(10)) : "";
}
async function api(url, data, headers={}) {
  const response = await fetch(url, {
    method: data === undefined ? "GET" : "POST",
    credentials:"same-origin",
    headers:{"Content-Type":"application/json", "X-CSRFToken":csrf(), ...headers},
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  let result;
  try { result = await response.json(); }
  catch (_) { throw new Error("Request failed (" + response.status + "). Refresh your session and retry."); }
  if (!response.ok) throw new Error(result.message || "Request failed (" + response.status + ").");
  return result;
}
let cart = null;
let checkoutAttempt = null;
function renderCart() {
  const container = document.getElementById("cart-items");
  if (!container || !cart) return;
  container.replaceChildren();
  if (!cart.items.length) {
    const empty=document.createElement("p");
    empty.className="empty"; empty.textContent="Add products to begin a purchase.";
    container.append(empty);
  }
  for (const item of cart.items) {
    const row=document.createElement("div"); row.className="cart-item";
    const info=document.createElement("span");
    const title=document.createElement("strong"); title.textContent=item.name;
    const detail=document.createElement("small"); detail.textContent=item.quantity + " × " + money(item.unit_price_minor);
    info.append(title,detail);
    const right=document.createElement("span");
    const price=document.createElement("strong"); price.textContent=money(item.total_minor);
    const remove=document.createElement("button"); remove.type="button"; remove.className="text-button"; remove.textContent="Remove";
    remove.addEventListener("click", async () => {
      remove.disabled=true;
      try { cart=await api("/api/cart/",{product_id:item.product_id,quantity:0}); checkoutAttempt=null; renderCart(); }
      catch(error) {notice(error.message,true); remove.disabled=false;}
    });
    right.append(price,remove); row.append(info,right); container.append(row);
  }
  document.getElementById("cart-total").textContent=money(cart.total_minor);
  document.getElementById("cart-count").textContent=String(cart.items.reduce((n,i)=>n+i.quantity,0));
}
document.querySelectorAll(".api-form").forEach(form => {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button=form.querySelector("button"); button.disabled=true;
    const data=Object.fromEntries(new FormData(form));
    delete data.csrfmiddlewaretoken;
    if ("delta" in data) data.delta=Number(data.delta);
    try {
      const result=await api(form.dataset.url,data);
      if (form.dataset.follow && result.url) window.location.assign(result.url);
      else window.location.reload();
    } catch(error) {notice(error.message,true); button.disabled=false;}
  });
});
document.querySelectorAll(".add-to-cart").forEach(form => {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button=form.querySelector("button"); button.disabled=true;
    try {
      if (!cart) cart=await api("/api/cart/");
      const id=Number(form.dataset.product);
      const old=cart.items.find(item=>item.product_id===id);
      cart=await api("/api/cart/",{product_id:id,quantity:(old ? old.quantity : 0)+Number(new FormData(form).get("quantity"))});
      checkoutAttempt=null; renderCart(); notice("Purchase cart updated.");
    } catch(error) {notice(error.message,true);}
    finally {button.disabled=false;}
  });
});
const checkoutForm=document.getElementById("checkout-form");
if (checkoutForm) {
  api("/api/cart/").then(value=>{cart=value;renderCart();}).catch(error=>notice(error.message,true));
  checkoutForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (!cart || !cart.items.length) {notice("Add a product before submitting your purchase.",true); return;}
    const button=checkoutForm.querySelector("button"); button.disabled=true;
    const fields=new FormData(checkoutForm);
    const data={warehouse_id:Number(fields.get("warehouse_id")),shipping_address:fields.get("shipping_address"),cart_version:cart.version};
    // Retain exactly the same request and key after an ambiguous network failure.
    if (!checkoutAttempt || JSON.stringify(checkoutAttempt.data)!==JSON.stringify(data)) {
      checkoutAttempt={key:crypto.randomUUID(),data};
    }
    try {
      const result=await api("/api/checkout/",checkoutAttempt.data,{"Idempotency-Key":checkoutAttempt.key});
      window.location.assign(result.url);
    } catch(error) {notice(error.message,true); button.disabled=false;}
  });
}

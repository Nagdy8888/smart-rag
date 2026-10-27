import { expect,test } from "@playwright/test";
import { signInLiveMember } from "./live-auth";

test("owner overview uses live aggregates and works on desktop and mobile",async({page,request})=>{
  const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
  await signInLiveMember(page,request);
  await page.setViewportSize({width:1440,height:1000});
  await page.goto("/admin");
  await expect(page.getByRole("tab",{name:"Overview",exact:true})).toHaveAttribute("aria-selected","true");
  await expect(page.getByRole("heading",{name:"Workspace overview"})).toBeVisible();
  await expect(page.getByText("Questions asked",{exact:true})).toBeVisible();
  await expect(page.getByText("Estimated AI cost",{exact:true})).toBeVisible();
  await expect(page.getByRole("region",{name:"Workspace overview",exact:true}).getByRole("alert")).toHaveCount(0);
  const response=page.waitForResponse(response=>response.url().includes("/admin/overview?days=7") && response.ok());
  await page.getByLabel("Reporting period").selectOption("7");
  const costResponse=await response;
  const payload=await costResponse.json();
  expect(payload.summary.cost_reporting).toHaveProperty("estimated_cost_usd");
  expect(payload.summary.cost_reporting).toHaveProperty("safety_allowance_usd");
  await expect(page.getByText("Admitted questions / last 7 days")).toBeVisible();
  const chart=page.getByRole("img",{name:/Questions over time. Use/});
  await chart.focus();await page.keyboard.press("Home");await page.keyboard.press("ArrowRight");
  await page.getByRole("heading",{name:"Workspace overview"}).scrollIntoViewIfNeeded();
  await page.screenshot({path:"../../.private-eval/overview-desktop.png",fullPage:true});
  await page.getByRole("heading",{name:"Answer outcomes",exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:"../../.private-eval/overview-desktop-outcomes.png"});
  await page.getByRole("heading",{name:"Estimated usage cost over time",exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:"../../.private-eval/overview-desktop-cost.png"});
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole("heading",{name:"Needs attention"})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.getByRole("heading",{name:"Workspace overview"}).scrollIntoViewIfNeeded();
  await page.screenshot({path:"../../.private-eval/overview-mobile.png",fullPage:true});
  for (const [title,name] of [["Needs attention","attention"],["Questions over time","activity"],["Answer outcomes","outcomes"],["Document authority","authority"],["Estimated usage cost over time","cost"]]) {
    await page.getByRole("heading",{name:title,exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:`../../.private-eval/overview-mobile-${name}.png`});
  }
  await page.getByRole("region",{name:"Questions over time",exact:true}).getByText("View daily data").click();
  await expect(page.getByRole("table")).toBeVisible();
  await page.goto("/admin?tab=usage");
  await expect(page.getByRole("heading",{name:"Understand your usage"})).toBeVisible();
  await expect(page.getByText("Estimated usage cost",{exact:true})).toHaveCount(2);
  await expect(page.getByText("How costs are calculated",{exact:true})).toHaveCount(2);
  expect(errors).toEqual([]);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../wp-content/plugins/ezb-core/ezb-core.php', import.meta.url), 'utf8');
const handler = source.slice(source.indexOf('function ezb_handle_quote_form()'), source.indexOf("add_action( 'admin_post_nopriv_ezb_quote'"));
assert.ok(handler.length > 100, 'quote handler must exist');
assert.match(source, /function ezb_quote_live_mail_authorized\(\)[\s\S]*?defined\( 'EZB_QUOTE_LIVE_MAIL_OWNER_APPROVED' \)/);
assert.match(source, /true === EZB_QUOTE_LIVE_MAIL_OWNER_APPROVED/, 'approval must be strict boolean true');
const gate = handler.indexOf('if ( ! ezb_quote_live_mail_authorized() )');
assert.ok(gate > 0 && gate < handler.indexOf('wp_mail('), 'approval gate must precede mail call');
assert.match(handler.slice(gate, handler.indexOf('wp_mail(')), /quote_status=preview/, 'unapproved submit must be discarded');
assert.match(source, /Preview only — no enquiry was sent\./, 'preview must never imply successful delivery');
assert.match(source, /ezb_quote_receipt_valid\(/, 'success must require a signed mail receipt');
assert.match(source, /ezb_quote_live_mail_authorized\(\) && ezb_quote_receipt_valid/, 'preview must never show sent status');
assert.match(handler, /quote_status=ignored/, 'honeypot must never report mail sent');
assert.match(handler, /quote_receipt=.*ezb_quote_receipt_issue/, 'successful mail redirect must carry receipt');
console.log('EZB_QUOTE_MAIL_AUTHORIZATION_GUARD_PASS cases=9');

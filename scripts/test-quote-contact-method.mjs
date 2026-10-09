import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const script = readFileSync(new URL('../wp-content/themes/ezb-theme/assets/js/site.js', import.meta.url), 'utf8');

function simulate({ reduced = false, formPresent = true, fieldsPresent = true } = {}) {
  const handlers = {};
  const phone = {
    value: '', error: '', reportCount: 0, focusCount: 0,
    focus() { this.focusCount += 1; },
    setCustomValidity(value) { this.error = value; },
    reportValidity() { this.reportCount += 1; return !this.error; },
    addEventListener(name, fn) { handlers['phone:' + name] = fn; }
  };
  const email = {
    value: '',
    addEventListener(name, fn) { handlers['email:' + name] = fn; }
  };
  const form = {
    querySelector(selector) {
      if (!fieldsPresent) return null;
      return selector === 'input[name="phone"]' ? phone :
        selector === 'input[name="email"]' ? email : null;
    },
    addEventListener(name, fn) { handlers['form:' + name] = fn; }
  };
  const document = {
    querySelectorAll(selector) {
      return selector === '.ezb-quote-form' && formPresent ? [form] : [];
    },
    documentElement: { classList: { add() {}, remove() {} } }
  };
  const window = {
    matchMedia() { return { matches: reduced, addEventListener() {} }; }
  };
  runInNewContext(script, { window, document });

  return {
    phone,
    email,
    handlers,
    send() {
      let prevented = false;
      handlers['form:submit']?.({ preventDefault() { prevented = true; } });
      return prevented;
    },
    enterPhone(value) {
      phone.value = value;
      handlers['phone:input']?.();
    },
    enterEmail(value) {
      email.value = value;
      handlers['email:input']?.();
    }
  };
}

const empty = simulate();
assert.equal(empty.send(), true, 'empty contact methods must block submission');
assert.match(empty.phone.error, /phone number or email address/);
assert.equal(empty.phone.reportCount, 1, 'browser validity feedback must be shown');
assert.equal(empty.phone.focusCount, 1, 'missing contact method must receive keyboard focus');

empty.enterEmail('visitor@example.com');
assert.equal(empty.phone.error, '', 'email input must clear stale phone error');
assert.equal(empty.send(), false, 'email-only enquiry must submit');

const phoneOnly = simulate();
phoneOnly.enterPhone('0400 123 456');
assert.equal(phoneOnly.send(), false, 'phone-only enquiry must submit');

const whitespace = simulate();
whitespace.enterPhone('   ');
whitespace.enterEmail('   ');
assert.equal(whitespace.send(), true, 'whitespace is not a contact method');
assert.equal(whitespace.phone.reportCount, 1);

const reduced = simulate({ reduced: true });
assert.equal(reduced.send(), true, 'reduced-motion setting must not disable form validation');
reduced.enterPhone('03 9000 0000');
assert.equal(reduced.send(), false);

const noFields = simulate({ fieldsPresent: false });
assert.equal(noFields.handlers['form:submit'], undefined, 'missing markup must degrade safely');
simulate({ formPresent: false });

console.log('EZB_QUOTE_CONTACT_METHOD_TEST_PASS cases=6');

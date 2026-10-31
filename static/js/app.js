/*
 * Brightloop front-end behaviours. Plain JavaScript, no build step.
 *
 *  - confirmation prompts     <form data-confirm="Really?">, <a data-confirm="...">
 *  - auto-submitting filters  <form data-autosubmit> (selects and date inputs)
 *  - auto-dismiss alerts      .alert[data-autodismiss]
 *  - print buttons            <button data-print>
 *  - line-item formsets       see initFormset() for the markup contract
 */
(function () {
  "use strict";

  const currency = document.body.dataset.currency || "";
  const formatMoney = (value) => {
    const number = Number.isFinite(value) ? value : 0;
    const sign = number < 0 ? "-" : "";
    return sign + currency + Math.abs(number).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  // --- confirmation prompts ------------------------------------------------
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (form.matches("form[data-confirm]") && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-confirm]");
    if (link && !window.confirm(link.dataset.confirm)) {
      event.preventDefault();
    }
  });

  // --- filters: submit on change for selects and dates ---------------------
  document.querySelectorAll("form[data-autosubmit]").forEach((form) => {
    form.querySelectorAll("select, input[type=date]").forEach((element) => {
      element.addEventListener("change", () => form.requestSubmit());
    });
  });

  // --- auto-dismiss success alerts ----------------------------------------
  document.querySelectorAll(".alert[data-autodismiss]").forEach((alert) => {
    window.setTimeout(() => {
      if (window.bootstrap && window.bootstrap.Alert) {
        window.bootstrap.Alert.getOrCreateInstance(alert).close();
      } else {
        alert.remove();
      }
    }, 5000);
  });

  // --- print ---------------------------------------------------------------
  document.querySelectorAll("[data-print]").forEach((button) => {
    button.addEventListener("click", () => window.print());
  });
  if (new URLSearchParams(window.location.search).get("print") === "1") {
    window.addEventListener("load", () => window.print());
  }

  // --- line-item formsets --------------------------------------------------
  //
  // <div data-formset data-prefix="lines">
  //   <table><tbody data-formset-body>
  //     <tr class="formset-row">               (one per form; hidden DELETE checkbox inside)
  //       <select data-field="variant">       (options may carry data-price)
  //       <input  data-field="quantity">
  //       <input  data-field="unit_price">
  //       <select data-field="taxes" multiple> (options carry data-rate, percentage)
  //       <td data-cell="line_total">
  //       <button data-formset-remove>
  //   </tbody></table>
  //   <template data-formset-empty> ...row markup with __prefix__... </template>
  //   <button data-formset-add>
  //   <span data-total="untaxed">, <span data-total="tax">, <span data-total="total">
  // </div>
  function initFormset(container) {
    const prefix = container.dataset.prefix;
    const body = container.querySelector("[data-formset-body]");
    const template = container.querySelector("[data-formset-empty]");
    const totalForms = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
    const addButton = container.querySelector("[data-formset-add]");

    const rowValues = (row) => {
      const read = (name) => {
        const input = row.querySelector(`[data-field="${name}"]`);
        return input ? parseFloat(input.value) || 0 : 0;
      };
      const taxes = row.querySelector('[data-field="taxes"]');
      let rate = 0;
      if (taxes) {
        Array.from(taxes.selectedOptions).forEach((option) => {
          rate += parseFloat(option.dataset.rate) || 0;
        });
      }
      const subtotal = read("quantity") * read("unit_price");
      const tax = (subtotal * rate) / 100;
      return { subtotal, tax, total: subtotal + tax };
    };

    const recalc = () => {
      let untaxed = 0;
      let tax = 0;
      container.querySelectorAll(".formset-row").forEach((row) => {
        if (row.hidden) return;
        const deleteBox = row.querySelector('input[type=checkbox][name$="-DELETE"]');
        if (deleteBox && deleteBox.checked) return;
        const values = rowValues(row);
        const cell = row.querySelector('[data-cell="line_total"]');
        if (cell) cell.textContent = formatMoney(values.total);
        untaxed += values.subtotal;
        tax += values.tax;
      });
      const write = (name, value) => {
        container.querySelectorAll(`[data-total="${name}"]`).forEach((el) => (el.textContent = formatMoney(value)));
      };
      write("untaxed", untaxed);
      write("tax", tax);
      write("total", untaxed + tax);
    };

    const wireRow = (row) => {
      row.querySelectorAll("[data-field]").forEach((input) => {
        input.addEventListener("input", recalc);
        input.addEventListener("change", recalc);
      });
      const variant = row.querySelector('[data-field="variant"]');
      const price = row.querySelector('[data-field="unit_price"]');
      if (variant && price) {
        variant.addEventListener("change", () => {
          const option = variant.selectedOptions[0];
          if (option && option.dataset.price !== undefined) {
            price.value = parseFloat(option.dataset.price).toFixed(2);
          }
          const taxes = row.querySelector('[data-field="taxes"]');
          if (option && taxes && option.dataset.taxes !== undefined) {
            const ids = option.dataset.taxes.split(",").filter(Boolean);
            Array.from(taxes.options).forEach((tax) => (tax.selected = ids.includes(tax.value)));
          }
          recalc();
        });
      }
      const remove = row.querySelector("[data-formset-remove]");
      if (remove) {
        remove.addEventListener("click", () => {
          const deleteBox = row.querySelector('input[type=checkbox][name$="-DELETE"]');
          if (deleteBox) {
            deleteBox.checked = true;
            row.hidden = true;
          } else {
            row.remove();
          }
          recalc();
        });
      }
    };

    container.querySelectorAll(".formset-row").forEach(wireRow);

    if (addButton && template && totalForms) {
      addButton.addEventListener("click", () => {
        const index = parseInt(totalForms.value, 10);
        const html = template.innerHTML.replace(/__prefix__/g, String(index));
        const fragment = document.createElement("tbody");
        fragment.innerHTML = html.trim();
        const row = fragment.querySelector(".formset-row") || fragment.firstElementChild;
        body.appendChild(row);
        totalForms.value = String(index + 1);
        wireRow(row);
        const first = row.querySelector("select, input");
        if (first) first.focus();
        recalc();
      });
    }

    recalc();
  }

  document.querySelectorAll("[data-formset]").forEach(initFormset);
})();

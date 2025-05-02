// scripts.js

// Search functionality for filtering engagement list
function searchClients() {
    let input, filter, table, rows, i, j, td, txtValue;
    input = document.getElementById('searchBar')
    filter = input.value.toUpperCase();
    table = document.getElementById('engagement-table');
    rows = table.getElementsByTagName("tr");

    for (i = 1; i < rows.length; i++) {
        let tds = rows[i].getElementsByTagName("td");
        let rowContainsFilter = false;

        for (j = 0; j < tds.length; j++) {
            td = tds[j];
            if (td) {
                txtValue = td.textContent || td.innerText;
                if (txtValue.toUpperCase().indexOf(filter) > -1) {
                    rowContainsFilter = true;
                    break;  // no need to check other TDs, so break the loop
                }
            }
        }

        rows[i].style.display = rowContainsFilter ? "" : "none";
    }
}

/////////////////////////// TIMESHEET SCRIPTS //////////////////////////////

// Loading engagement_id into Time and Expense Modal Entry Forms //

const timeModal = document.getElementById('time-modal')
timeModal.addEventListener('show.bs.modal', event => {
    //get data-id attribute of clicked event
    let engagementID = $(event.relatedTarget).data("engagement-id")
    //populate the input field
    $(event.currentTarget).find('input[name="engagement-input"]').val(engagementID)
});

const expenseModal = document.getElementById('expense-modal')
expenseModal.addEventListener('show.bs.modal', event => {
    let engagementID = $(event.relatedTarget).data("engagement-id")
    $(event.currentTarget).find('input[name="expense-input"]').val(engagementID)
});


// Edit Timesheet Entries on Current and Review Timesheet Pages //
$(document).ready(function () {
// Handle "Edit" button clicks
    $('.edit-time-entry-button').click(function () {
        let tsID = $(this).data('ts-id');
        let editTsForm = $('#editTimeForm');

        // Fetch details using AJAX
        $.ajax({
            url: '/get_ts/' + tsID + '/',
            type: 'GET',
            success: function (data) {
                //Populate from fields with task details
                editTsForm.find('#ts-id').val(tsID)
                editTsForm.find('#id_engagement').val(data.engagement)
                editTsForm.find('#id_ts_date').val(data.ts_date)
                editTsForm.find('#id_hours').val(data.hours)
                editTsForm.find('#id_time_type_id').val(data.btype)
                editTsForm.find('#id_note').val(data.note)
            }
        })
    })
})


// Edit Expense Entries on Current and Review Timesheet Pages //
const editExpenseModal = document.getElementById('edit-expense-modal');

editExpenseModal.addEventListener('show.bs.modal', event => {
    let expID = $(event.relatedTarget).data("exp-id");
    let editExpForm = $('#editExpForm')
    console.log(expID)

    // Fetch details using AJAX
    $.ajax({
        url: '/get_expense/' + expID + '/',
        type: 'GET',
        success: function (data) {
            //Populate From fields with task details
            editExpForm.find('#exp-id').val(expID)
            editExpForm.find('#id_date').val(data.expense_date)
            editExpForm.find('#id_engagement').val(data.engagement)
            editExpForm.find('#id_expense_category').val(data.category)
            editExpForm.find('#id_expense_amount').val(data.expense_amount)
            editExpForm.find('#id_time_type_id').val(data.btype)
            editExpForm.find('#id_expense_note').val(data.note)
        }
    })
})

// Showing Expense Day List Functionality on Current & Review Timesheet Pages //
const expenseDayModal = document.getElementById('view-expense-modal');

expenseDayModal.addEventListener('hidden.bs.modal', event=> {
    let expenseTableBody = document.querySelector("#expense-table tbody")
    while (expenseTableBody.firstChild) {
        expenseTableBody.removeChild(expenseTableBody.firstChild)
    }
})

expenseDayModal.addEventListener('show.bs.modal', event=> {
    let dte = $(event.relatedTarget).data("dt")
    let tableBody = document.querySelector("#expense-table tbody")
    document.getElementById('expense-day-text').innerText = dte

    $.ajax({
        url:'/get_expense_list/' + dte + '/',
        type: 'GET',
        success: function (expenseDayList) {
            expenseDayList.forEach(item => {
                let row = document.createElement('tr')
                let expenseID = item.expense_id
                let url = `/delete-expense-current/${item.expense_id}/`
                row.innerHTML = `
                                    <td>${item.engagement__provider} - ${item.engagement__provider__provider_name}</td>
                                    <td>${item.engagement__time_code} - ${item.engagement__time_code__time_code_desc }</td>
                                    <td>${item.expense_category__expense_category}</td>
                                    <td>${item.expense_amount}</td>
                                    <td>${item.time_type_id}</td>
                                    <td class="text-center">
                                        <a type="button" class="srg-link edit-expense-button" data-bs-toggle="modal" href="#edit-expense-modal" data-exp-id="${expenseID}">
                                          <i class="bi bi-pencil-square"></i>
                                        </a>
    
                                        <a type="button" class="srg-link-danger" href="${url}">
                                          <i class="bi bi-trash3"></i>
                                        </a>
                                    </td>
                                `
                tableBody.appendChild(row)
            })
        }
    })
})
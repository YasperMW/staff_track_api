import io
from datetime import datetime
from typing import List, Dict, Any, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

styles = getSampleStyleSheet()


class ReportColors:
    header_bg = colors.HexColor('#1E88E5')
    header_text = colors.white
    alternate_row = colors.HexColor('#F5F5F5')
    border = colors.HexColor('#E0E0E0')
    sky_blue = colors.HexColor('#1E88E5')


def create_header_style():
    return ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=ReportColors.sky_blue
    )


def create_subheader_style():
    return ParagraphStyle(
        'SubHeader',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=10,
        alignment=TA_CENTER,
        textColor=colors.darkgrey
    )


def create_normal_style():
    return ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=5
    )


def generate_attendance_pdf(
    buffer: io.BytesIO,
    records: List[Dict[str, Any]],
    start_date: str,
    end_date: str,
    user_name: str,
    user_department: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None
):
    """Generate a PDF report for individual staff attendance with summary and detailed records"""
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    
    elements = []
    
    # Title - department name as title if available, otherwise generic
    title = f"{user_department} Attendance Report" if user_department else "Attendance Report"
    elements.append(Paragraph(title, create_header_style()))
    
    # Employee info
    info_data = [
        ['Employee:', user_name],
        ['Period:', f'{start_date} to {end_date}'],
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (1, -1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Summary section
    if summary:
        elements.append(Paragraph("Attendance Summary", create_subheader_style()))
        
        total_days = summary.get('total_days', 0)
        present_days = summary.get('present_days', 0)
        absent_days = summary.get('absent_days', 0)
        on_time = summary.get('on_time', 0)
        late = summary.get('late', 0)
        early_out = summary.get('early_out', 0)
        total_hours = summary.get('total_work_hours', 0)
        avg_hours = summary.get('avg_hours', 0)
        
        summary_data = [
            ['Days Present', 'Days Absent', 'On Time', 'Late', 'Early Out', 'Total Hours', 'Avg Hours'],
            [str(present_days), str(absent_days), str(on_time), str(late), str(early_out), f'{total_hours:.1f}h', f'{avg_hours:.1f}h'],
        ]
        
        summary_table = Table(summary_data, colWidths=[1.2*inch, 1.2*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.2*inch, 1.2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (6, 0), ReportColors.header_bg),
            ('TEXTCOLOR', (0, 0), (6, 0), ReportColors.header_text),
            ('FONTNAME', (0, 0), (6, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (6, -1), 10),
            ('ALIGN', (0, 0), (6, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (6, -1), 8),
            ('TOPPADDING', (0, 0), (6, -1), 8),
            ('GRID', (0, 0), (6, -1), 1, ReportColors.border),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))
    
    # Records table
    elements.append(Paragraph("Detailed Attendance Records", create_subheader_style()))
    
    table_data = [['#', 'Date', 'Check-in Time', 'Check-out Time', 'Shift Type', 'Work Hours', 'Late Reason', 'Early Check-out Reason']]
    
    for i, record in enumerate(records, 1):
        check_in = record.get('check_in_time', 'N/A')
        check_out = record.get('check_out_time', 'N/A')
        late_reason = record.get('late_reason', '-')
        early_reason = record.get('early_checkout_reason', '-')
        
        # Truncate long reasons
        if late_reason and len(str(late_reason)) > 20:
            late_reason = str(late_reason)[:17] + '...'
        if early_reason and len(str(early_reason)) > 20:
            early_reason = str(early_reason)[:17] + '...'
        
        work_hours = record.get('work_hours')
        work_hours_str = f'{work_hours:.1f}h' if work_hours else '-'
        
        table_data.append([
            str(i),
            record.get('date', 'N/A'),
            check_in,
            check_out,
            record.get('shift_type', 'N/A') or 'Day Shift',
            work_hours_str,
            str(late_reason),
            str(early_reason),
        ])
    
    # Create table
    col_widths = [0.4*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1.5*inch, 1*inch, 1.5*inch, 1.8*inch]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ReportColors.header_bg),
        ('TEXTCOLOR', (0, 0), (-1, 0), ReportColors.header_text),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),
        ('ALIGN', (3, 1), (3, -1), 'CENTER'),
        ('ALIGN', (5, 1), (5, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, ReportColors.border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ReportColors.alternate_row]),
    ]))
    
    elements.append(table)
    
    # Footer
    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle('Footer', fontSize=8, textColor=colors.grey, alignment=TA_RIGHT)
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", footer_style))
    
    doc.build(elements)
    return buffer


def generate_department_summary_pdf(
    buffer: io.BytesIO,
    staff_records: List[Dict[str, Any]],
    start_date: str,
    end_date: str,
    department_name: str,
    total_staff: int
):
    """Generate a PDF report for department attendance summary"""
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    
    elements = []
    
    # Title - department name as the title
    elements.append(Paragraph(f"{department_name} Attendance Report", create_header_style()))
    
    # Period info
    info_data = [
        ['Period:', f'{start_date} to {end_date}'],
        ['Total Staff:', str(total_staff)],
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (1, -1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Staff attendance summary table
    elements.append(Paragraph("Staff Attendance Summary", create_subheader_style()))
    
    table_data = [['#', 'Employee Name', 'Days Present', 'Days Absent', 'On Time', 'Late', 'Early Out', 'Total Hours', 'Avg Hours']]
    
    for i, record in enumerate(staff_records, 1):
        table_data.append([
            str(i),
            record.get('staff_name', 'N/A'),
            str(record.get('days_present', 0)),
            str(record.get('days_absent', 0)),
            str(record.get('on_time', 0)),
            str(record.get('late', 0)),
            str(record.get('early_out', 0)),
            f"{record.get('total_hours', 0):.1f}h",
            f"{record.get('avg_hours', 0):.1f}h",
        ])
    
    col_widths = [0.4*inch, 1.5*inch, 0.9*inch, 0.9*inch, 0.8*inch, 0.8*inch, 0.9*inch, 1.0*inch, 0.9*inch]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ReportColors.header_bg),
        ('TEXTCOLOR', (0, 0), (-1, 0), ReportColors.header_text),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (8, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, ReportColors.border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ReportColors.alternate_row]),
    ]))
    
    elements.append(table)
    
    # Footer
    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle('Footer', fontSize=8, textColor=colors.grey, alignment=TA_RIGHT)
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", footer_style))
    
    doc.build(elements)
    return buffer